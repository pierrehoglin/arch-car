#!/usr/bin/env python3
"""
Service control: SSH, Bluetooth, wifi.

    svc status                  # everything at a glance
    svc status ssh
    svc on ssh
    svc off ssh
    svc toggle bluetooth
    svc restart bluetooth
    svc enable ssh              # start at boot
    svc disable ssh

`svc status` includes the hotspot, but the verbs do not: starting
hostapd without first releasing wlan0 from NetworkManager fails. Use
the `hotspot` command, which handles that handover.

Needs a polkit rule granting manage-units for these units; see
carlib/system/services.py for it.
"""

import sys
import argparse

from carlib.system import services
from carlib.core.output import run, emit_json, global_flags, parse_args


def show(state) -> None:
    mark = 'on ' if state.active else 'off'
    boot = 'boot' if state.enabled_at_boot else '    '
    print(f'{mark}  {boot}  {state.name:<10} {state.active_state}'
          f'{"/" + state.sub_state if state.sub_state else ""}')
    if state.followers:
        for unit, unit_state in state.followers.items():
            print(f'            \u2514 {unit:<20} {unit_state}')


async def cmd_status(args) -> None:
    if args.service:
        state = await services.status(args.service)
        if args.json:
            emit_json(state)
        else:
            show(state)
        return

    states = await services.status_all()
    if args.json:
        emit_json(states)
        return
    for state in states:
        show(state)


async def cmd_on(args) -> None:
    state = await services.start(args.service)
    show(state) if not args.json else emit_json(state)


async def cmd_off(args) -> None:
    state = await services.stop(args.service)
    show(state) if not args.json else emit_json(state)


async def cmd_toggle(args) -> None:
    state = await services.toggle(args.service)
    show(state) if not args.json else emit_json(state)


async def cmd_restart(args) -> None:
    state = await services.restart(args.service)
    show(state) if not args.json else emit_json(state)


async def cmd_enable(args) -> None:
    state = await services.set_enabled(args.service, True)
    show(state) if not args.json else emit_json(state)


async def cmd_disable(args) -> None:
    state = await services.set_enabled(args.service, False)
    show(state) if not args.json else emit_json(state)


def main() -> int:
    common = global_flags('--json')

    ap = argparse.ArgumentParser(
        description=__doc__.strip(),
        parents=[common],
        formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)

    # Everything services knows about, for read-only status.
    READABLE = sorted(services.SERVICES)

    # What the verbs may act on. The hotspot is excluded: starting
    # hostapd without first releasing wlan0 from NetworkManager fails,
    # and carlib.system.hotspot is what handles that handover. argparse
    # enforces this before a handler ever runs.
    CONTROLLABLE = [n for n in READABLE if n != 'hotspot']

    p = sub.add_parser('status', parents=[common],
                       help='show service state')
    p.set_defaults(fn=cmd_status)
    p.add_argument('service', nargs='?', choices=READABLE,
                   help=f'one of: {", ".join(READABLE)}')

    for name, fn, help_text in (
            ('on', cmd_on, 'start a service'),
            ('off', cmd_off, 'stop a service'),
            ('toggle', cmd_toggle, 'start or stop depending on state'),
            ('restart', cmd_restart, 'restart a service'),
            ('enable', cmd_enable, 'start at boot'),
            ('disable', cmd_disable, 'do not start at boot')):
        sp = sub.add_parser(name, parents=[common], help=help_text)
        sp.set_defaults(fn=fn)
        sp.add_argument('service', choices=CONTROLLABLE,
                        help=f'one of: {", ".join(CONTROLLABLE)}')

    args = parse_args(ap, defaults={'json': False})
    return run(args.fn(args))


if __name__ == '__main__':
    sys.exit(main())
