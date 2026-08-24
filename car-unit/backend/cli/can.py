#!/usr/bin/env python3
"""
CAN bus inspection over socketcan.

    ./can interfaces                # what the kernel has
    ./can dump                      # live frames
    ./can dump --id 1A0 --id 7E8    # filter by arbitration ID
    ./can dump --limit 100 --json
    ./can sniff --duration 30       # summarise what is on the bus
    ./can send 1A0 1234ABCD         # transmit one frame

Bring an interface up first. Powertrain buses are usually 500 kbit/s:

    sudo ip link set can0 type can bitrate 500000
    sudo ip link set can0 up

To experiment without a car, socketcan provides a virtual bus:

    sudo modprobe vcan
    sudo ip link add dev vcan0 type vcan
    sudo ip link set up vcan0

Writing to a live vehicle bus can change how the car behaves. Read
first, and test sends on vcan0.
"""

import sys
import argparse

from carlib.vehicle import can
from carlib.core.output import run, emit_json


async def cmd_interfaces(args) -> None:
    found = can.interfaces()
    if args.json:
        emit_json([{'name': n, 'up': can.is_up(n)} for n in found])
        return

    if not found:
        print('No CAN interfaces.')
        print('Create one:  sudo ip link set can0 type can bitrate 500000')
        return

    for name in found:
        state = 'up' if can.is_up(name) else 'down'
        print(f'{name:<10} {state}')


async def cmd_dump(args) -> None:
    ids = {int(x, 16) for x in args.id} if args.id else None

    if not args.json:
        target = f' (ids: {", ".join(args.id)})' if args.id else ''
        print(f'listening on {args.channel}{target} -- ctrl-c to stop')

    async for frame in can.listen(args.channel, ids=ids, limit=args.limit):
        if args.json:
            emit_json(frame)
            continue

        line = str(frame)
        signals = can.decode(frame)
        if signals:
            line += '   ' + ', '.join(str(s) for s in signals)
        print(line)


async def cmd_sniff(args) -> None:
    if not args.json:
        print(f'sampling {args.channel} for {args.duration}s...')

    stats, latest = await can.sniff(args.channel, args.duration)

    if args.json:
        emit_json({
            'stats': stats.to_dict(),
            'frames': [f.to_dict() for f in latest.values()],
        })
        return

    if not stats.frames:
        print('No frames. Is the bus wired and at the right bitrate?')
        return

    print(f'\n{stats.frames} frames, {len(stats.unique_ids)} unique IDs, '
          f'{stats.rate:.0f}/s')
    if stats.errors:
        print(f'{stats.errors} error frames -- check bitrate and wiring')

    print(f'\n{"ID":>8}  {"LEN":>3}  DATA')
    for fid in sorted(latest):
        frame = latest[fid]
        line = (f'{frame.hex_id:>8}  {frame.dlc:>3}  '
                f'{frame.data.hex(" ").upper()}')
        signals = can.decode(frame)
        if signals:
            line += '   ' + ', '.join(str(s) for s in signals)
        print(line)

    known = can.known_ids()
    if known:
        print(f'\ndecoders registered for: '
              f'{", ".join(f"{i:X}" for i in known)}', file=sys.stderr)


async def cmd_send(args) -> None:
    try:
        arbitration_id = int(args.can_id, 16)
        data = bytes.fromhex(args.data)
    except ValueError as exc:
        raise ValueError(f'bad hex: {exc}') from exc

    if len(data) > 8:
        raise ValueError('classic CAN carries at most 8 bytes')

    await can.send(args.channel, arbitration_id, data, args.extended)
    print(f'sent {arbitration_id:X}  [{len(data)}]  '
          f'{data.hex(" ").upper()}  on {args.channel}')


def main() -> int:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument('--json', action='store_true')
    common.add_argument('-c', '--channel', default='can0',
                        help='CAN interface (default: can0)')

    ap = argparse.ArgumentParser(
        description=__doc__.strip(),
        parents=[common],
        formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)

    p = sub.add_parser('interfaces', parents=[common],
                       help='list CAN interfaces')
    p.set_defaults(fn=cmd_interfaces)

    p = sub.add_parser('dump', parents=[common], help='print live frames')
    p.set_defaults(fn=cmd_dump)
    p.add_argument('--id', action='append', metavar='HEX',
                   help='only this arbitration ID, repeatable')
    p.add_argument('--limit', type=int, help='stop after N frames')

    p = sub.add_parser('sniff', parents=[common],
                       help='summarise what is on the bus')
    p.set_defaults(fn=cmd_sniff)
    p.add_argument('--duration', type=float, default=10.0)

    p = sub.add_parser('send', parents=[common], help='transmit one frame')
    p.set_defaults(fn=cmd_send)
    p.add_argument('can_id', metavar='ID', help='arbitration ID in hex')
    p.add_argument('data', help='payload in hex, e.g. 1234ABCD')
    p.add_argument('--extended', action='store_true',
                   help='29-bit identifier')

    args = ap.parse_args()
    return run(args.fn(args))


if __name__ == '__main__':
    sys.exit(main())
