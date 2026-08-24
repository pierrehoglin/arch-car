#!/usr/bin/env python3
"""
Audio volume.

    audio                       # current volume
    audio 50                    # set to 50%
    audio up / audio down       # step by 5
    audio up 10                 # step by 10
    audio mute / audio unmute / audio toggle
    audio devices               # list sinks and sources
    audio default 52            # switch to another sink
    audio mic / audio mic 80

Runs against the user session's PipeWire, so a system service will not
find it -- run anything using this as a user unit.
"""

import sys
import argparse

from carlib.system import audio
from carlib.core.output import run, emit_json

STEP = 5


def show(vol) -> None:
    state = ' [muted]' if vol.muted else ''
    print(f'{vol.bars}  {vol.percent}%{state}')


async def cmd_get(args) -> None:
    vol = await audio.get()
    emit_json(vol) if args.json else show(vol)


async def cmd_set(args) -> None:
    vol = await audio.set_volume(args.percent)
    emit_json(vol) if args.json else show(vol)


async def cmd_up(args) -> None:
    vol = await audio.adjust(args.step)
    emit_json(vol) if args.json else show(vol)


async def cmd_down(args) -> None:
    vol = await audio.adjust(-args.step)
    emit_json(vol) if args.json else show(vol)


async def cmd_mute(args) -> None:
    vol = await audio.set_muted(True)
    emit_json(vol) if args.json else show(vol)


async def cmd_unmute(args) -> None:
    vol = await audio.set_muted(False)
    emit_json(vol) if args.json else show(vol)


async def cmd_toggle(args) -> None:
    vol = await audio.toggle_mute()
    emit_json(vol) if args.json else show(vol)


async def cmd_devices(args) -> None:
    found = await audio.devices()
    if args.json:
        emit_json(found)
        return
    if not found:
        print('No audio devices.')
        return
    for d in found:
        mark = '*' if d.is_default else ' '
        print(f'{mark} {d.node_id:>4}  {d.kind:<7} {d.name}')
    print('\n* default', file=sys.stderr)


async def cmd_default(args) -> None:
    found = await audio.set_default(args.node_id)
    for d in found:
        if d.is_default:
            print(f'default {d.kind}: {d.name}')


async def cmd_mic(args) -> None:
    if args.percent is None:
        vol = await audio.microphone()
    else:
        vol = await audio.set_microphone(args.percent)
    emit_json(vol) if args.json else show(vol)


async def cmd_waybar(args) -> None:
    """One JSON line for a status bar."""
    import json
    try:
        vol = await audio.get()
    except Exception:
        print(json.dumps({'text': '', 'class': 'unavailable'}))
        return

    if vol.muted:
        glyph = '\U000f075f'
    elif vol.percent == 0:
        glyph = '\U000f075f'
    elif vol.percent < 34:
        glyph = '\U000f057f'
    elif vol.percent < 67:
        glyph = '\U000f0580'
    else:
        glyph = '\U000f057e'

    print(json.dumps({
        'text': f'{glyph}  {vol.percent}%',
        'alt': 'muted' if vol.muted else 'normal',
        'class': 'muted' if vol.muted else 'normal',
        'percentage': vol.percent,
    }))


def main() -> int:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument('--json', action='store_true')

    ap = argparse.ArgumentParser(
        description=__doc__.strip(),
        parents=[common],
        formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd')

    for name, fn, help_text in (
            ('get', cmd_get, 'current volume'),
            ('mute', cmd_mute, 'mute'),
            ('unmute', cmd_unmute, 'unmute'),
            ('toggle', cmd_toggle, 'flip mute'),
            ('devices', cmd_devices, 'list sinks and sources'),
            ('waybar', cmd_waybar, 'one JSON line for a status bar')):
        sp = sub.add_parser(name, parents=[common], help=help_text)
        sp.set_defaults(fn=fn)

    p = sub.add_parser('set', parents=[common], help='set volume')
    p.set_defaults(fn=cmd_set)
    p.add_argument('percent', type=int)

    p = sub.add_parser('up', parents=[common], help='raise volume')
    p.set_defaults(fn=cmd_up)
    p.add_argument('step', type=int, nargs='?', default=STEP)

    p = sub.add_parser('down', parents=[common], help='lower volume')
    p.set_defaults(fn=cmd_down)
    p.add_argument('step', type=int, nargs='?', default=STEP)

    p = sub.add_parser('default', parents=[common],
                       help='switch the default sink')
    p.set_defaults(fn=cmd_default)
    p.add_argument('node_id', type=int, help='from `audio devices`')

    p = sub.add_parser('mic', parents=[common],
                       help='microphone volume')
    p.set_defaults(fn=cmd_mic)
    p.add_argument('percent', type=int, nargs='?', default=None)

    # `audio 50` with no subcommand sets the volume.
    argv = sys.argv[1:]
    if argv and argv[0].lstrip('-').isdigit() and not argv[0].startswith('-'):
        argv = ['set'] + argv

    args = ap.parse_args(argv)
    if args.cmd is None:
        args = ap.parse_args(['get'])

    return run(args.fn(args))


if __name__ == '__main__':
    sys.exit(main())
