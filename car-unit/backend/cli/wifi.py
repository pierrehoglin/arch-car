#!/usr/bin/env python3
"""
WiFi control.

    wifi status
    wifi list                       # scan for networks
    wifi list --cached              # skip the rescan, faster
    wifi connect Wifit
    wifi connect Wifit --password secret
    wifi disconnect
    wifi on / wifi off / wifi toggle
    wifi saved
    wifi forget Wifit

Connecting without --password reuses a saved profile, so you only need
the password the first time.

No sudo needed: NetworkManager's own polkit rules already permit a
local user to manage connections.
"""

import sys
import getpass
import argparse

from carlib.system import wifi
from carlib.core.output import run, emit_json


def show_status(state) -> None:
    if not state.enabled:
        print('wifi off')
        return
    if not state.connected:
        print(f'wifi on, not connected  ({state.device})')
        return
    print(f'{state.ssid}')
    print(f'  device: {state.device}')
    print(f'  signal: {state.signal}%')
    print(f'  ip:     {state.ip_address or "-"}')


async def cmd_status(args) -> None:
    state = await wifi.status()
    emit_json(state) if args.json else show_status(state)


async def cmd_list(args) -> None:
    networks = await wifi.scan(rescan=not args.cached)
    if args.json:
        emit_json(networks)
        return

    if not networks:
        print('No networks found.')
        return

    width = max(len(n.ssid) for n in networks)
    for n in networks:
        mark = '*' if n.in_use else ('+' if n.saved else ' ')
        lock = '  ' if n.open else '\U000f033e'
        print(f'{mark} {n.bars}  {n.signal:>3}%  {lock} '
              f'{n.ssid:<{width}}  {n.security}')
    print('\n* connected   + saved', file=sys.stderr)


async def cmd_connect(args) -> None:
    password = args.password
    if args.ask_password:
        password = getpass.getpass('Password: ')

    state = await wifi.connect(args.ssid, password)
    emit_json(state) if args.json else show_status(state)


async def cmd_disconnect(args) -> None:
    state = await wifi.disconnect()
    emit_json(state) if args.json else show_status(state)


async def cmd_on(args) -> None:
    state = await wifi.set_enabled(True)
    emit_json(state) if args.json else show_status(state)


async def cmd_off(args) -> None:
    state = await wifi.set_enabled(False)
    emit_json(state) if args.json else show_status(state)


async def cmd_toggle(args) -> None:
    state = await wifi.toggle()
    emit_json(state) if args.json else show_status(state)


async def cmd_saved(args) -> None:
    names = await wifi.saved_networks()
    if args.json:
        emit_json(names)
        return
    if not names:
        print('No saved networks.')
        return
    for name in names:
        print(name)


async def cmd_forget(args) -> None:
    await wifi.forget(args.ssid)
    print(f'forgot {args.ssid}')


def main() -> int:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument('--json', action='store_true')

    ap = argparse.ArgumentParser(
        description=__doc__.strip(),
        parents=[common],
        formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)

    for name, fn, help_text in (
            ('status', cmd_status, 'connection state'),
            ('disconnect', cmd_disconnect, 'drop the connection'),
            ('on', cmd_on, 'turn the radio on'),
            ('off', cmd_off, 'turn the radio off'),
            ('toggle', cmd_toggle, 'flip the radio'),
            ('saved', cmd_saved, 'list saved profiles')):
        sp = sub.add_parser(name, parents=[common], help=help_text)
        sp.set_defaults(fn=fn)

    p = sub.add_parser('list', parents=[common],
                       help='scan for networks')
    p.set_defaults(fn=cmd_list)
    p.add_argument('--cached', action='store_true',
                   help='use the cached list instead of rescanning')

    p = sub.add_parser('connect', parents=[common], help='join a network')
    p.set_defaults(fn=cmd_connect)
    p.add_argument('ssid')
    p.add_argument('--password', help='only needed the first time')
    p.add_argument('--ask-password', action='store_true',
                   help='prompt instead of passing on the command line')

    p = sub.add_parser('forget', parents=[common],
                       help='delete a saved profile')
    p.set_defaults(fn=cmd_forget)
    p.add_argument('ssid')

    args = ap.parse_args()
    return run(args.fn(args))


if __name__ == '__main__':
    sys.exit(main())
