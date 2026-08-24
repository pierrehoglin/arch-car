#!/usr/bin/env python3
"""
WiFi hotspot control.

    hotspot                     # status
    hotspot on
    hotspot off
    hotspot toggle
    hotspot restart
    hotspot clients             # who is connected
    hotspot waybar              # one JSON line for a status bar
    hotspot --json

The Pi has one radio, so turning the hotspot on releases wlan0 from
NetworkManager and turning it off hands it back. Clients get whichever
uplink the Pi is using -- LTE in the car, ethernet on the desk.

Needs a polkit rule granting manage-units for hostapd.service, and
NetworkManager access for the interface handover.
"""

import sys
import json
import argparse

from carlib.system import hotspot
from carlib.core.output import run, emit_json, global_flags, parse_args

GLYPH_ON = '\U000f0a0c'         # nf-md-access_point_network
GLYPH_OFF = '\U000f0a0b'        # nf-md-access_point_network_off


def show(state) -> None:
    if not state.active:
        print('hotspot off')
        if state.ssid:
            print(f'  ssid:  {state.ssid} (configured)')
        return

    print(f'{state.ssid or "hotspot"}  on')
    print(f'  channel:  {state.channel or "-"}  {state.band}')
    print(f'  address:  {state.address or "-"}')
    print(f'  uplink:   {state.uplink or "none"}')
    print(f'  clients:  {state.client_count}')

    for client in state.clients:
        print(f'      {client.ip:<15} {client.mac}  {client.hostname}')

    if state.followers:
        unhealthy = [u for u, s in state.followers.items()
                     if s != 'active']
        if unhealthy:
            print(f'\n  not running: {", ".join(unhealthy)}',
                  file=sys.stderr)

    if not state.uplink:
        print('\nNo default route -- clients will associate but have no '
              'internet.', file=sys.stderr)


async def cmd_status(args) -> None:
    state = await hotspot.status()
    emit_json(state) if args.json else show(state)


async def cmd_on(args) -> None:
    state = await hotspot.start()
    emit_json(state) if args.json else show(state)


async def cmd_off(args) -> None:
    state = await hotspot.stop()
    emit_json(state) if args.json else show(state)


async def cmd_toggle(args) -> None:
    state = await hotspot.toggle()
    emit_json(state) if args.json else show(state)


async def cmd_restart(args) -> None:
    state = await hotspot.restart()
    emit_json(state) if args.json else show(state)


async def cmd_clients(args) -> None:
    state = await hotspot.status()
    if args.json:
        emit_json(state.clients)
        return

    if not state.active:
        print('hotspot off')
        return
    if not state.clients:
        print('no clients connected')
        return

    width = max(len(c.hostname or '?') for c in state.clients)
    for c in state.clients:
        print(f'{c.ip:<15}  {c.mac}  {(c.hostname or "?"):<{width}}')


async def cmd_waybar(args) -> None:
    """One JSON line for a Waybar custom module."""
    try:
        state = await hotspot.status()
    except Exception:
        print(json.dumps({'text': GLYPH_OFF, 'alt': 'off',
                          'class': 'off', 'tooltip': 'unavailable'}))
        return

    if not state.active:
        print(json.dumps({
            'text': GLYPH_OFF,
            'alt': 'off',
            'class': 'off',
            'tooltip': 'hotspot off',
        }, ensure_ascii=False))
        return

    count = state.client_count
    text = f'{GLYPH_ON}  {count}' if count else GLYPH_ON

    names = '\n'.join(f'  {c.ip}  {c.label}' for c in state.clients)
    tooltip = (f'{state.ssid or "hotspot"}\n'
               f'uplink: {state.uplink or "none"}\n'
               f'{count} client{"" if count == 1 else "s"}'
               + (f'\n{names}' if names else ''))

    print(json.dumps({
        'text': text,
        'alt': 'on',
        'class': 'on' if state.uplink else 'no-uplink',
        'tooltip': tooltip,
    }, ensure_ascii=False))


def main() -> int:
    common = global_flags('--json')

    ap = argparse.ArgumentParser(
        description=__doc__.strip(),
        parents=[common],
        formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd')

    for name, fn, help_text in (
            ('status', cmd_status, 'current state'),
            ('on', cmd_on, 'start the hotspot'),
            ('off', cmd_off, 'stop the hotspot'),
            ('toggle', cmd_toggle, 'flip the hotspot'),
            ('restart', cmd_restart, 'stop and start'),
            ('clients', cmd_clients, 'list connected devices'),
            ('waybar', cmd_waybar, 'one JSON line for a status bar')):
        sp = sub.add_parser(name, parents=[common], help=help_text)
        sp.set_defaults(fn=fn)

    args = parse_args(ap, 'status', defaults={'json': False})
    return run(args.fn(args))


if __name__ == '__main__':
    sys.exit(main())
