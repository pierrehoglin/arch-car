#!/usr/bin/env python3
"""
FM radio via RTL-SDR.

    fm                          # what is playing
    fm play 92.7
    fm play P3                  # by preset name
    fm stop
    fm up / fm down             # step 0.1 MHz
    fm next / fm prev           # step through presets
    fm presets
    fm save 92.7 P3
    fm forget 92.7
    fm devices
    fm waybar

Frequencies accept most forms: 92.7, 92,7, 92.7M, 92700000.

Needs rtl-sdr and sox:

    sudo pacman -S rtl-sdr sox

Playback runs in the background and survives this command exiting, so
`fm play` then `fm stop` from a later invocation works.
"""

import sys
import json
import argparse

from carlib.radio import fm
from carlib.core.output import run, emit_json, global_flags, parse_args

GLYPH_ON = '\U000f043d'         # nf-md-radio
GLYPH_OFF = '\U000f043e'        # nf-md-radio_off

STEP = 0.1


def show(state) -> None:
    if not state.playing:
        print('radio off')
        return

    print(state.label)
    print(f'  frequency: {state.frequency:.1f} MHz')
    if state.name:
        print(f'  station:   {state.name}')
    print(f'  gain:      {state.gain:g} dB')
    print(f'  playing:   {state.uptime}s')


async def cmd_status(args) -> None:
    state = await fm.status()
    emit_json(state) if args.json else show(state)


async def cmd_play(args) -> None:
    state = await fm.play(args.station, gain=args.gain,
                          device=args.device, squelch=args.squelch)
    emit_json(state) if args.json else show(state)


async def cmd_stop(args) -> None:
    state = await fm.stop()
    emit_json(state) if args.json else print('radio off')


async def cmd_up(args) -> None:
    state = await fm.tune(args.step)
    emit_json(state) if args.json else show(state)


async def cmd_down(args) -> None:
    state = await fm.tune(-args.step)
    emit_json(state) if args.json else show(state)


async def cmd_next(args) -> None:
    state = await fm.next_preset(1)
    emit_json(state) if args.json else show(state)


async def cmd_prev(args) -> None:
    state = await fm.next_preset(-1)
    emit_json(state) if args.json else show(state)


async def cmd_presets(args) -> None:
    stations = fm.load_presets()
    if args.json:
        emit_json(stations)
        return
    if not stations:
        print('no presets')
        print('add one with: fm save 92.7 P3', file=sys.stderr)
        return

    current = await fm.status()
    for station in stations:
        mark = '*' if (current.playing and current.frequency is not None
                       and abs(station.frequency - current.frequency) < 0.01
                       ) else ' '
        print(f'{mark} {station.frequency:>6.1f}  {station.name}')


async def cmd_save(args) -> None:
    frequency = fm.parse_frequency(args.station)
    fm.add_preset(frequency, args.name or '')
    print(f'saved {frequency:.1f}'
          f'{" as " + args.name if args.name else ""}')


async def cmd_forget(args) -> None:
    frequency = fm.parse_frequency(args.station)
    fm.remove_preset(frequency)
    print(f'removed {frequency:.1f}')


async def cmd_devices(args) -> None:
    found = await fm.devices()
    if args.json:
        emit_json(found)
        return
    if not found:
        print('no RTL-SDR devices found')
        print('check the dongle is plugged in and the DVB driver is '
              'blacklisted', file=sys.stderr)
        return
    for i, name in enumerate(found):
        print(f'{i}  {name}')


async def cmd_waybar(args) -> None:
    """One JSON line for a Waybar custom module."""
    try:
        state = await fm.status()
    except Exception:
        print(json.dumps({'text': GLYPH_OFF, 'alt': 'off',
                          'class': 'off', 'tooltip': 'unavailable'}))
        return

    if not state.playing:
        print(json.dumps({
            'text': GLYPH_OFF,
            'alt': 'off',
            'class': 'off',
            'tooltip': 'radio off',
        }, ensure_ascii=False))
        return

    print(json.dumps({
        'text': f'{GLYPH_ON}  {state.label}',
        'alt': 'on',
        'class': 'on',
        'tooltip': (f'{state.frequency:.1f} MHz'
                    f'{" · " + state.name if state.name else ""}\n'
                    f'gain {state.gain:g} dB · {state.uptime}s'),
    }, ensure_ascii=False))


def main() -> int:
    common = global_flags('--json')

    ap = argparse.ArgumentParser(
        description=__doc__.strip(),
        parents=[common],
        formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd')

    for name, fn, help_text in (
            ('status', cmd_status, 'what is playing'),
            ('stop', cmd_stop, 'stop playback'),
            ('next', cmd_next, 'next preset'),
            ('prev', cmd_prev, 'previous preset'),
            ('presets', cmd_presets, 'list saved stations'),
            ('devices', cmd_devices, 'list RTL-SDR dongles'),
            ('waybar', cmd_waybar, 'one JSON line for a status bar')):
        sp = sub.add_parser(name, parents=[common], help=help_text)
        sp.set_defaults(fn=fn)

    p = sub.add_parser('play', parents=[common],
                       help='tune and play')
    p.set_defaults(fn=cmd_play)
    p.add_argument('station', help='frequency or preset name')
    p.add_argument('--gain', type=float, default=fm.DEFAULT_GAIN,
                   help=f'tuner gain in dB (default {fm.DEFAULT_GAIN:g})')
    p.add_argument('--device', type=int, default=0)
    p.add_argument('--squelch', type=int, default=0,
                   help='silence below this level; 0 disables')

    for name, fn, help_text in (
            ('up', cmd_up, 'step frequency up'),
            ('down', cmd_down, 'step frequency down')):
        sp = sub.add_parser(name, parents=[common], help=help_text)
        sp.set_defaults(fn=fn)
        sp.add_argument('step', type=float, nargs='?', default=STEP,
                        help=f'MHz to step (default {STEP})')

    p = sub.add_parser('save', parents=[common], help='save a preset')
    p.set_defaults(fn=cmd_save)
    p.add_argument('station')
    p.add_argument('name', nargs='?', default='')

    p = sub.add_parser('forget', parents=[common],
                       help='remove a preset')
    p.set_defaults(fn=cmd_forget)
    p.add_argument('station')

    args = parse_args(ap, 'status', defaults={'json': False})
    return run(args.fn(args))


if __name__ == '__main__':
    sys.exit(main())
