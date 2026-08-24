#!/usr/bin/env python3
"""
Playback control over Bluetooth AVRCP.

    ./bt-media players
    ./bt-media status
    ./bt-media toggle
    ./bt-media next
    ./bt-media monitor                  # live track changes
    ./bt-media waybar                   # one JSON line for a status bar

The player selector is optional when one phone is connected:

    ./bt-media next "Pierre Pixel"

The MediaPlayer1 object only exists once the phone has an active media
session -- if `players` is empty, start playback on the phone once.
"""

import sys
import json
import argparse

from carlib.bluetooth import media
from carlib.core.output import (
    run, emit_json, add_target, STATUS_GLYPH, global_flags, parse_args)


async def cmd_players(args) -> None:
    found = await media.players()
    if args.json:
        emit_json(found)
        return

    if not found:
        print('No media players.')
        print('Connect the phone with A2DP, then start playback once so '
              'AVRCP registers a player.')
        return

    for p in found:
        glyph = STATUS_GLYPH.get(p.status, '')
        print(f'{p.device_name}  [{p.status}] {glyph}')
        print(f'  path:  {p.path}')
        if p.track.label:
            print(f'  track: {p.track.label}')


async def cmd_status(args) -> None:
    p = await media.status(args.target)
    if args.json:
        emit_json(p)
        return

    glyph = STATUS_GLYPH.get(p.status, '')
    print(f'{p.device_name}  {glyph} {p.status}')
    if p.track.title:
        print(f'  title:  {p.track.title}')
    if p.track.artist:
        print(f'  artist: {p.track.artist}')
    if p.track.album:
        print(f'  album:  {p.track.album}')
    if p.track.duration:
        print(f'  time:   {media.format_ms(p.position)} / '
              f'{media.format_ms(p.track.duration)}')


async def cmd_control(args) -> None:
    p = await media.control(args.cmd, args.target)
    print(f'{args.cmd}: {p.device_name}')


async def cmd_monitor(args) -> None:
    p = await media.status(args.target)
    glyph = STATUS_GLYPH.get(p.status, '')
    print(f'watching {p.device_name} (ctrl-c to stop)')
    print(f'{glyph} {p.status:<8} {p.track.label}')

    async for kind, data in media.watch(args.target):
        if kind == 'track':
            label = ' - '.join(x for x in (data.get('artist'),
                                           data.get('title')) if x)
            print(f'  track: {label}')
        elif kind == 'status':
            st = data['status']
            print(f'  {STATUS_GLYPH.get(st, "")} {st}')


async def cmd_waybar(args) -> None:
    """One JSON line for a Waybar custom module."""
    try:
        p = await media.status(args.target)
    except Exception:
        print(json.dumps({'text': '', 'class': 'disconnected'}))
        return

    glyph = STATUS_GLYPH.get(p.status, '')
    label = p.track.label
    print(json.dumps({
        'text': f'{glyph}  {label}' if label else glyph,
        'alt': p.status,
        'class': p.status,
        'tooltip': '\n'.join(x for x in (p.track.title, p.track.artist,
                                         p.track.album) if x),
    }, ensure_ascii=False))


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__.strip(),
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--json', action='store_true')
    sub = ap.add_subparsers(dest='cmd', required=True)

    p = sub.add_parser('players', help='list media players')
    p.set_defaults(fn=cmd_players, target=None)

    for name, fn, help_text in (
            ('status', cmd_status, 'show what is playing'),
            ('monitor', cmd_monitor, 'watch track and status changes'),
            ('waybar', cmd_waybar, 'one JSON line for a status bar')):
        sp = sub.add_parser(name, help=help_text)
        sp.set_defaults(fn=fn)
        add_target(sp, required=False)

    for action in ('play', 'pause', 'stop', 'toggle', 'next', 'prev',
                   'forward', 'rewind'):
        sp = sub.add_parser(action, help=f'{action} playback')
        sp.set_defaults(fn=cmd_control)
        add_target(sp, required=False)

    args = parse_args(ap, defaults={'json': False})
    return run(args.fn(args))


if __name__ == '__main__':
    sys.exit(main())
