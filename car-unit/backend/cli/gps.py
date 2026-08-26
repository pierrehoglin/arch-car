#!/usr/bin/env python3
"""
GPS and location via ModemManager.

    ./gps modems                    # discover, check capabilities
    ./gps enable                    # turn on NMEA + raw GPS
    ./gps enable --assisted         # add A-GPS (needs data)
    ./gps status                    # what is enabled right now
    ./gps get                       # one fix
    ./gps get --json
    ./gps watch                     # live updates, ctrl-c to stop
    ./gps sats                      # satellite detail
    ./gps rate 1                    # refresh every second
    ./gps supl supl.google.com:7275
    ./gps disable

A cold start takes several minutes with the antenna outdoors. Until
then `get` reports no fix but still shows the coarse cell location.

Needs polkit authorisation, or sudo. To avoid sudo:

    /etc/polkit-1/rules.d/50-modemmanager.rules
    polkit.addRule(function(action, subject) {
        if (action.id.indexOf("org.freedesktop.ModemManager1.") === 0 &&
            subject.user == "alarm") {
            return polkit.Result.YES;
        }
    });
"""

import sys
import json
import argparse
from datetime import datetime

from carlib.location import gps as location
from carlib.core.output import (
    run, emit_json, add_target, dash, global_flags, parse_args)

# Nerd Font glyph. Empty box means the font is missing:
# pacman -S ttf-nerd-fonts-symbols
GLYPH = '\U000f0471'        # nf-md-crosshairs_gps



def show_fix(fix) -> None:
    if not fix.has_fix:
        print('no fix')
        print(f'  mode:       {fix.mode}')
        print(f'  quality:    {fix.quality}')
        print(f'  satellites: {fix.satellites_used} used, '
              f'{fix.satellites_visible} visible')
        if fix.cell_id:
            print(f'  cell:       mcc={fix.cell_mcc} mnc={fix.cell_mnc} '
                  f'lac={fix.cell_lac} id={fix.cell_id}')
        print('\nCold starts take minutes. Antenna needs sky view.',
              file=sys.stderr)
        return

    print(fix.format_coordinates())
    print(f'  decimal:    {fix.latitude:.6f}, {fix.longitude:.6f}')
    print(f'  altitude:   {dash(fix.altitude, " m")}')
    print(f'  mode:       {fix.mode} ({fix.quality})')
    print(f'  speed:      {dash(fix.speed_kmh, " km/h")}')
    print(f'  heading:    {dash(fix.heading, " deg")}')
    print(f'  satellites: {fix.satellites_used} used, '
          f'{fix.satellites_visible} visible')
    print(f'  hdop:       {dash(fix.hdop)}')
    print(f'  utc:        {dash(fix.utc)}')
    print(f'  map:        {fix.maps_url}')


async def cmd_modems(args) -> None:
    found = await location.modems()
    if args.json:
        emit_json(found)
        return

    if not found:
        print('No modems. Is ModemManager running?')
        return

    for m in found:
        print(f'{m.model or "?"}  [{m.state}]')
        print(f'  path:         {m.path}')
        print(f'  operator:     {m.operator or "-"}')
        print(f'  signal:       {m.signal_quality}%  {m.access_technology}')
        print(f'  location:     {", ".join(m.location_capabilities) or "-"}')
        print(f'  enabled:      {", ".join(m.location_enabled) or "none"}')
        if m.has_gps and not m.gps_active:
            print('  -> GPS available but off; run `enable`')


async def cmd_enable(args) -> None:
    m = await location.enable(
        args.target,
        nmea=not args.no_nmea,
        raw=not args.no_raw,
        assisted=args.assisted,
        signal_changes=True,
    )
    print(f'enabled: {", ".join(m.location_enabled) or "none"}')
    if args.assisted:
        print('A-GPS needs a working data connection to help.',
              file=sys.stderr)


async def cmd_ensure(args) -> None:
    """Enable GPS only if it is off. Safe to run repeatedly."""
    result = await location.ensure_enabled(
        args.target,
        nmea=not args.no_nmea,
        raw=not args.no_raw,
        assisted=args.assisted,
        refresh_rate=args.rate,
    )
    if args.json:
        emit_json(result)
        return

    print(result.reason)
    if result.modem:
        print(f'  {result.modem.model or result.modem.path}')
        print(f'  sources: '
              f'{", ".join(result.modem.location_enabled) or "none"}')
    if result.rate_changed:
        print(f'  refresh rate set to {args.rate}s')


async def cmd_supervise(args) -> None:
    """
    Keep GPS enabled for as long as this runs.

    Location gathering resets when ModemManager restarts or the modem
    re-enumerates, so a one-shot enable at boot is not enough.
    """
    print(f'supervising (every {args.interval}s, ctrl-c to stop)',
          file=sys.stderr)

    async for event in location.supervise(
            interval=args.interval,
            match=args.target,
            nmea=not args.no_nmea,
            raw=not args.no_raw,
            assisted=args.assisted,
            refresh_rate=args.rate):

        if args.json:
            emit_json(event)
            continue

        stamp = datetime.now().strftime('%H:%M:%S')
        mark = '*' if event.changed else ' '
        print(f'{stamp} {mark} {event.reason}', flush=True)


async def cmd_disable(args) -> None:
    await location.disable(args.target)
    print('location gathering disabled')


async def cmd_status(args) -> None:
    info = await location.status(args.target)
    if args.json:
        emit_json(info)
        return

    m = info['modem']
    print(f'{m["model"] or "?"}  [{m["state"]}]')
    print(f'  capabilities:     {", ".join(info["capabilities"]) or "-"}')
    print(f'  enabled:          {", ".join(info["enabled"]) or "none"}')
    print(f'  refresh rate:     {info["refresh_rate"]}s')
    print(f'  signals changes:  {info["signals_location"]}')
    print(f'  supl server:      {info["supl_server"] or "-"}')

    if not info['signals_location']:
        print('\n`watch` needs signalling; re-run `enable`.', file=sys.stderr)


async def cmd_get(args) -> None:
    fix = await location.get(args.target)
    if args.json:
        emit_json(fix)
    else:
        show_fix(fix)


async def cmd_sats(args) -> None:
    fix = await location.get(args.target)
    if args.json:
        emit_json(fix.satellites)
        return

    if not fix.satellites:
        print('No satellites reported yet.')
        return

    print(f'{"PRN":>4}  {"ELEV":>4}  {"AZIM":>4}  {"SNR":>4}  USED')
    for s in fix.satellites:
        bar = '#' * ((s.snr or 0) // 5)
        print(f'{s.prn:>4}  {dash(s.elevation):>4}  {dash(s.azimuth):>4}  '
              f'{dash(s.snr):>4}  {"*" if s.used else " "}    {bar}')
    print(f'\n{fix.satellites_used} used of {len(fix.satellites)} tracked',
          file=sys.stderr)


async def cmd_waybar(args) -> None:
    """
    One JSON line for a Waybar custom module.

    Two classes: `on` when GPS is enabled and reporting, `off` when
    there is no modem or location gathering is not enabled. A fix is
    not required for `on` -- a receiver tracking satellites but still
    working towards a fix is working, and showing that is the point of
    the satellite count.
    """
    try:
        state = await location.status(args.target)
        enabled = state['enabled']
        gps_on = 'gps-nmea' in enabled or 'gps-raw' in enabled
    except Exception:
        print(json.dumps({
            'text': GLYPH,
            'alt': 'off',
            'class': 'off',
            'tooltip': 'no modem',
        }, ensure_ascii=False))
        return

    if not gps_on:
        print(json.dumps({
            'text': GLYPH,
            'alt': 'off',
            'class': 'off',
            'tooltip': 'GPS not enabled',
        }, ensure_ascii=False))
        return

    try:
        fix = await location.get(args.target)
    except Exception:
        print(json.dumps({
            'text': GLYPH,
            'alt': 'off',
            'class': 'off',
            'tooltip': 'cannot read location',
        }, ensure_ascii=False))
        return

    used = fix.satellites_used
    visible = fix.satellites_visible

    if fix.has_fix:
        tooltip = (f'{fix.format_coordinates()}\n'
                   f'{fix.mode} fix \u00b7 {used}/{visible} satellites\n'
                   f'hdop {dash(fix.hdop)}')
    else:
        tooltip = (f'no fix\n'
                   f'{used}/{visible} satellites\n'
                   f'cold starts take minutes')

    print(json.dumps({
        'text': f'{GLYPH}  {used}',
        'alt': 'on',
        'class': 'on',
        'tooltip': tooltip,
    }, ensure_ascii=False))


async def cmd_watch(args) -> None:
    print('watching for position updates (ctrl-c to stop)')
    async for fix in location.watch(args.target):
        if args.json:
            emit_json(fix)
        elif fix.has_fix:
            print(f'{fix.format_coordinates()}  '
                  f'{dash(fix.speed_kmh, " km/h")}  '
                  f'{fix.satellites_used} sats')
        else:
            print(f'no fix  ({fix.satellites_visible} visible)')


async def cmd_rate(args) -> None:
    rate = await location.set_refresh_rate(args.seconds, args.target)
    print(f'refresh rate: {rate}s')


async def cmd_supl(args) -> None:
    await location.set_supl_server(args.server, args.target)
    print(f'supl server: {args.server}')


def main() -> int:
    # A parent parser so --json works either side of the subcommand:
    # `gps --json get` and `gps get --json` both parse.
    common = global_flags('--json')

    ap = argparse.ArgumentParser(
        description=__doc__.strip(),
        parents=[common],
        formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)

    p = sub.add_parser('modems', parents=[common],
                       help='list modems and GPS capabilities')
    p.set_defaults(fn=cmd_modems, target=None)

    for name, fn, help_text in (
            ('status', cmd_status, 'what is enabled right now'),
            ('get', cmd_get, 'read the current position'),
            ('sats', cmd_sats, 'satellite detail'),
            ('watch', cmd_watch, 'live position updates'),
            ('waybar', cmd_waybar, 'one JSON line for a status bar'),
            ('disable', cmd_disable, 'turn location gathering off')):
        sp = sub.add_parser(name, parents=[common], help=help_text)
        sp.set_defaults(fn=fn)
        add_target(sp, required=False)

    p = sub.add_parser('enable', parents=[common],
                       help='turn on location gathering')
    p.set_defaults(fn=cmd_enable)
    add_target(p, required=False)
    p.add_argument('--assisted', action='store_true',
                   help='enable A-GPS for a faster first fix')
    p.add_argument('--no-nmea', action='store_true')
    p.add_argument('--no-raw', action='store_true')

    p = sub.add_parser('ensure', parents=[common],
                       help='enable only if off; safe to repeat')
    p.set_defaults(fn=cmd_ensure)
    add_target(p, required=False)
    p.add_argument('--rate', type=int, default=1,
                   help='refresh rate in seconds (default 1)')
    p.add_argument('--assisted', action='store_true')
    p.add_argument('--no-nmea', action='store_true')
    p.add_argument('--no-raw', action='store_true')

    p = sub.add_parser('supervise', parents=[common],
                       help='keep GPS enabled; for a systemd service')
    p.set_defaults(fn=cmd_supervise)
    add_target(p, required=False)
    p.add_argument('--interval', type=float, default=10.0,
                   help='seconds between checks (default 10)')
    p.add_argument('--rate', type=int, default=1,
                   help='refresh rate in seconds (default 1)')
    p.add_argument('--assisted', action='store_true')
    p.add_argument('--no-nmea', action='store_true')
    p.add_argument('--no-raw', action='store_true')

    p = sub.add_parser('rate', parents=[common],
                       help='set the GPS refresh rate')
    p.set_defaults(fn=cmd_rate)
    p.add_argument('seconds', type=int)
    add_target(p, required=False)

    p = sub.add_parser('supl', parents=[common],
                       help='set the A-GPS SUPL server')
    p.set_defaults(fn=cmd_supl)
    p.add_argument('server', help='e.g. supl.google.com:7275')
    add_target(p, required=False)

    args = parse_args(ap, defaults={'json': False})
    return run(args.fn(args))


if __name__ == '__main__':
    sys.exit(main())
