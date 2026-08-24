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
# Nerd Font glyphs. Empty boxes mean the font is missing:
# pacman -S ttf-nerd-fonts-symbols
GLYPH_DISCONNECTED = '\U000f08fd'   # nf-md-network_strength_off_outline
GLYPH_BARS = {
    0: '\U000f08fe',                # network-strength-outline
    1: '\U000f08f4',                # network-strength-1
    2: '\U000f08f6',                # network-strength-2
    3: '\U000f08f8',                # network-strength-3
    4: '\U000f08fa',                # network-strength-4
}


def pick_glyph(state) -> str:
    """
    Two states only: connected with a strength, or disconnected.

    Anything short of a live bearer -- no modem, searching, registered
    but not connected -- renders the same, because from the driver's
    seat there is no useful distinction.
    """
    if not state.present or not state.connected:
        return GLYPH_DISCONNECTED
    bars = min(4, max(0, round(state.signal / 25)))
    return GLYPH_BARS[bars]


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
    """
    One JSON line for a Waybar custom module.

    Two classes only: connected or disconnected. The stalled case --
    bearer up, carrier discarding traffic -- still shows as connected,
    because the icon is a signal indicator, not a diagnostic. The
    tooltip carries the byte counters if you want to check.
    """
    try:
        state = await lte.status()
    except Exception:
        print(json.dumps({
            'text': GLYPH_DISCONNECTED,
            'alt': 'disconnected',
            'class': 'disconnected',
            'tooltip': 'modem unavailable',
        }))
        return

    glyph = pick_glyph(state)

    if not state.present or not state.connected:
        print(json.dumps({
            'text': glyph,
            'alt': 'disconnected',
            'class': 'disconnected',
            'tooltip': state.summary,
        }, ensure_ascii=False))
        return

    text = f'{glyph}  {state.access_technology.upper()}' \
        if args.show_tech else glyph

    print(json.dumps({
        'text': text,
        'alt': 'connected',
        'class': 'connected',
        'tooltip': (f'{state.operator}\n'
                    f'{state.access_technology} \u00b7 {state.signal}%\n'
                    f'{state.ip_address}\n'
                    f'{lte.format_bytes(state.bytes_rx)} down / '
                    f'{lte.format_bytes(state.bytes_tx)} up'),
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
