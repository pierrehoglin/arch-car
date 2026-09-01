#!/usr/bin/env python3
"""
Audio source selection.

    source                      # what is playing
    source list
    source select fm
    source select spotifyd
    source pause
    source toggle
    source ta-skip              # end a traffic announcement early
    source waybar

PipeWire mixes everything by default, so without arbitration the radio
and Spotify play over each other. `select` pauses the others.

Arbitration runs inside the carlib daemon, not here: it watches for a
source starting on its own, which matters because Spotify Connect
begins playback from your phone with nothing calling into carlib at
all. Watch what it decides with:

    journalctl --user -u carlib -f

The supervisor also handles traffic announcements: when the tuned
station raises its TA flag, the radio takes over and whatever was
playing is restored when the bulletin ends. That only works while the
FM pipeline is running, which is why pausing the radio mutes it rather
than stopping it.

Turn that off with `settings set fm.traffic false`, which takes effect
without restarting the supervisor.

Requires playerctl:

    sudo pacman -S playerctl
"""

import sys
import json
import argparse

# Talks to the carlib daemon rather than the library directly: it owns
# the runtime state and runs the source supervisor.
from carlib.api.client import source
from carlib.core.output import run, emit_json, global_flags, parse_args

GLYPH = '\U000f075a'            # nf-md-speaker


def show(state) -> None:
    if not state.players:
        print('no sources')
        print('nothing is registered -- start the radio, or pick the '
              'car in Spotify', file=sys.stderr)
        return

    width = max(len(p.name) for p in state.players)

    for player in state.players:
        mark = '>' if player.playing else ' '
        detail = player.label if player.label != player.name else ''
        print(f'{mark} {player.name:<{width}}  {player.status:<8} '
              f'{detail}')

    if state.traffic:
        print('\ntraffic announcement in progress', file=sys.stderr)

    if state.conflict:
        print('\nmore than one source is playing -- the carlib '
              'daemon should have arbitrated;\ncheck '
              '`systemctl --user status carlib`', file=sys.stderr)


async def cmd_status(args) -> None:
    state = await source.status()
    emit_json(state) if args.json else show(state)


async def cmd_select(args) -> None:
    state = await source.select(args.name)
    emit_json(state) if args.json else show(state)


async def cmd_pause(args) -> None:
    paused = await source.pause_others(keep='')
    if args.json:
        emit_json(paused)
        return
    print(f'paused: {", ".join(paused)}' if paused else 'nothing playing')


async def cmd_toggle(args) -> None:
    state = await source.toggle_play()
    emit_json(state) if args.json else show(state)


async def cmd_ta_skip(args) -> None:
    """End the current traffic announcement early."""
    skipped = await source.request_ta_skip()
    if args.json:
        emit_json({'skipped': skipped})
        return

    if skipped:
        print('skipping the announcement')
    else:
        print('no announcement to skip')


async def cmd_waybar(args) -> None:
    """One JSON line for a Waybar custom module."""
    try:
        state = await source.status()
    except Exception:
        print(json.dumps({'text': GLYPH, 'alt': 'off',
                          'class': 'off', 'tooltip': 'unavailable'},
                         ensure_ascii=False))
        return

    playing = [p for p in state.players if p.playing]

    if not playing:
        print(json.dumps({
            'text': GLYPH,
            'alt': 'off',
            'class': 'off',
            'tooltip': 'nothing playing',
        }, ensure_ascii=False))
        return

    current = playing[0]
    lines = [f'{p.name}: {p.status}' for p in state.players]

    print(json.dumps({
        'text': f'{GLYPH}  {current.label}',
        'alt': 'on',
        'class': 'on',
        'tooltip': '\n'.join(lines),
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
            ('list', cmd_status, 'same as status'),
            ('pause', cmd_pause, 'pause everything'),
            ('toggle', cmd_toggle, 'play or pause the current source'),
            ('ta-skip', cmd_ta_skip,
             'end the current traffic announcement'),
            ('waybar', cmd_waybar, 'one JSON line for a status bar')):
        sp = sub.add_parser(name, parents=[common], help=help_text)
        sp.set_defaults(fn=fn)

    p = sub.add_parser('select', parents=[common],
                       help='make one source the active one')
    p.set_defaults(fn=cmd_select)
    p.add_argument('name', help='fm, spotifyd, ... see `source list`')

    args = parse_args(ap, 'status', defaults={'json': False})
    return run(args.fn(args))


if __name__ == '__main__':
    sys.exit(main())
