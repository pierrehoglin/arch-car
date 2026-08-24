#!/usr/bin/env python3
"""
SMS and MMS over Bluetooth MAP.

    ./bt-messages 20:F0:94:03:AB:DF folders     # verify access first
    ./bt-messages 20:F0:94:03:AB:DF filters
    ./bt-messages 20:F0:94:03:AB:DF list
    ./bt-messages 20:F0:94:03:AB:DF list --folder sent --count 50
    ./bt-messages 20:F0:94:03:AB:DF read <handle>
    ./bt-messages 20:F0:94:03:AB:DF send +46701234567 'text'

Needs message access granted for this device on the phone -- a separate
toggle from contact sharing -- and obexd running.

Sending is the least reliable part: some phones accept the push and
never transmit. Check the phone's own outbox afterwards.
"""

import sys
import argparse

from carlib.bluetooth import messages
from carlib.core.output import run, emit_json, global_flags, parse_args


async def cmd_folders(args) -> None:
    found = await messages.folders(args.address)
    if args.json:
        emit_json(found)
        return
    for name in found:
        print(name)


async def cmd_filters(args) -> None:
    for field in await messages.filter_fields(args.address):
        print(field)


async def cmd_list(args) -> None:
    headers = await messages.listing(args.address, args.folder, args.count)
    if args.json:
        emit_json(headers)
        return

    if not headers:
        print(f'No messages in {args.folder}.')
        return

    for m in headers:
        mark = ' ' if m.read else '*'
        print(f'{mark} {m.timestamp:<16} {m.who:<22} {m.subject[:50]}')
        print(f'    {m.handle}')
    print(f'\n{len(headers)} messages in {args.folder}', file=sys.stderr)


async def cmd_read(args) -> None:
    body = await messages.read(args.address, args.handle, args.raw)
    if args.json:
        emit_json(body)
        return
    print(f'from: {body.sender or body.sender_number or "unknown"}')
    if body.status:
        print(f'status: {body.status}')
    print()
    print(body.body)


async def cmd_send(args) -> None:
    await messages.send(args.address, args.number, args.text)
    print(f'pushed to {args.number}')
    print('check the phone\'s outbox -- not every phone transmits these',
          file=sys.stderr)


async def cmd_update(args) -> None:
    await messages.update_inbox(args.address)
    print('inbox update requested')


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__.strip(),
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('address', help='phone MAC')
    ap.add_argument('--json', action='store_true')
    sub = ap.add_subparsers(dest='cmd', required=True)

    sub.add_parser('folders', help='list message folders'
                   ).set_defaults(fn=cmd_folders)
    sub.add_parser('filters', help='supported filter fields'
                   ).set_defaults(fn=cmd_filters)
    sub.add_parser('update', help='ask the phone to refresh its inbox'
                   ).set_defaults(fn=cmd_update)

    p = sub.add_parser('list', help='list message headers')
    p.set_defaults(fn=cmd_list)
    p.add_argument('--folder', default='inbox', choices=messages.FOLDERS)
    p.add_argument('--count', type=int, default=25,
                   help='0 for no limit')

    p = sub.add_parser('read', help='fetch one message body')
    p.set_defaults(fn=cmd_read)
    p.add_argument('handle', help='object path from `list`')
    p.add_argument('--raw', metavar='FILE')

    p = sub.add_parser('send', help='send an SMS (support varies)')
    p.set_defaults(fn=cmd_send)
    p.add_argument('number')
    p.add_argument('text')

    args = parse_args(ap, defaults={'json': False})
    return run(args.fn(args))


if __name__ == '__main__':
    sys.exit(main())
