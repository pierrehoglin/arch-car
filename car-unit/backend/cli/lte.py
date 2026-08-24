#!/usr/bin/env python3
"""
LTE connection status.

    lte                     # current state
    lte --json
    lte waybar              # one JSON line for a status bar
    lte watch               # refresh every few seconds

Reads ModemManager rather than NetworkManager, so it can report signal
strength, access technology and whether the bearer is actually carrying
bytes — a bearer can be up with the carrier discarding everything.
"""

import sys
import json
import asyncio
import argparse

from carlib.system import lte
from carlib.core.output import run, emit_json, dash, global_flags, parse_args

# Nerd Font glyphs. Empty boxes mean the font is missing:
# pacman -S ttf-nerd-fonts-symbols
GLYPH_OFF = '\U000f10dd'        # signal-off
GLYPH_NO_SIM = '\U000f0f31'     # sim-off
GLYPH_SEARCH = '\U000f08c1'     # signal-searching
GLYPH_BARS = {
    0: '\U000f0a61',            # signal-cellular-outline
    1: '\U000f0a5f',            # signal-cellular-1
    2: '\U000f0a60',            # signal-cellular-2
    3: '\U000f0a61',            # signal-cellular-3
    4: '\U000f0a61',
}


def pick_glyph(state) -> str:
    if not state.present:
        return GLYPH_NO_SIM
    if not state.connected:
        return GLYPH_SEARCH if state.state in ('searching', 'enabled',
                                               'registered') else GLYPH_OFF
    bars = min(4, max(0, round(state.signal / 25)))
    return GLYPH_BARS.get(bars, GLYPH_BARS[0])


def show(state) -> None:
    if not state.present:
        print(state.state)
        return

    print(f'{state.summary}')
    print(f'  modem:      {state.state}')
    print(f'  registered: {dash(state.registration)}')
    print(f'  signal:     {state.bars}  {state.signal}%')

    if not state.connected:
        print('  bearer:     not connected')
        return

    print(f'  interface:  {dash(state.interface)}')
    print(f'  ip:         {dash(state.ip_address)}')
    print(f'  apn:        {dash(state.apn)}')
    print(f'  traffic:    {lte.format_bytes(state.bytes_rx)} down / '
          f'{lte.format_bytes(state.bytes_tx)} up'
          f'  over {lte.format_duration(state.duration)}')

    if not state.carrying:
        print('\nBearer is up but almost nothing has come back. That '
              'usually means\nthe carrier is not routing — a '
              'subscription matter, not config.',
              file=sys.stderr)


async def cmd_status(args) -> None:
    state = await lte.status()
    emit_json(state) if args.json else show(state)


async def cmd_waybar(args) -> None:
    """One JSON line for a Waybar custom module."""
    try:
        state = await lte.status()
    except Exception:
        print(json.dumps({'text': GLYPH_OFF, 'class': 'unavailable',
                          'tooltip': 'modem unavailable'}))
        return

    glyph = pick_glyph(state)

    if not state.present:
        css = 'absent'
        text = glyph
        tooltip = state.state
    elif not state.connected:
        css = 'disconnected'
        text = glyph
        tooltip = f'{state.state}\n{state.operator or "no operator"}'
    else:
        css = 'connected' if state.carrying else 'stalled'
        text = f'{glyph}  {state.access_technology.upper()}' \
            if args.show_tech else glyph
        tooltip = (f'{state.operator}\n'
                   f'{state.access_technology} · {state.signal}%\n'
                   f'{state.ip_address}\n'
                   f'{lte.format_bytes(state.bytes_rx)} down / '
                   f'{lte.format_bytes(state.bytes_tx)} up')

    print(json.dumps({
        'text': text,
        'alt': css,
        'class': css,
        'tooltip': tooltip,
        'percentage': state.signal,
    }, ensure_ascii=False))


async def cmd_watch(args) -> None:
    print('watching (ctrl-c to stop)')
    while True:
        state = await lte.status()
        line = (f'{state.bars} {state.signal:>3}%  '
                f'{state.access_technology:<6} '
                f'{"up  " if state.connected else "down"}  '
                f'{lte.format_bytes(state.bytes_rx)} down')
        print(line)
        await asyncio.sleep(args.interval)


def main() -> int:
    common = global_flags('--json')

    ap = argparse.ArgumentParser(
        description=__doc__.strip(),
        parents=[common],
        formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd')

    p = sub.add_parser('status', parents=[common], help='current state')
    p.set_defaults(fn=cmd_status)

    p = sub.add_parser('waybar', parents=[common],
                       help='one JSON line for a status bar')
    p.set_defaults(fn=cmd_waybar)
    p.add_argument('--show-tech', action='store_true',
                   help='include LTE/5G next to the icon')

    p = sub.add_parser('watch', parents=[common], help='refresh in a loop')
    p.set_defaults(fn=cmd_watch)
    p.add_argument('--interval', type=float, default=5.0)

    args = parse_args(ap, 'status', defaults={'json': False})

    return run(args.fn(args))


if __name__ == '__main__':
    sys.exit(main())
