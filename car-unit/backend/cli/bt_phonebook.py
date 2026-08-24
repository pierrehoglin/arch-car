#!/usr/bin/env python3
"""
Contacts and call logs over Bluetooth PBAP.

    ./bt-phonebook 20:F0:94:03:AB:DF
    ./bt-phonebook 20:F0:94:03:AB:DF --book cch      # all calls
    ./bt-phonebook 20:F0:94:03:AB:DF --book mch      # missed
    ./bt-phonebook 20:F0:94:03:AB:DF --json
    ./bt-phonebook 20:F0:94:03:AB:DF --size
    ./bt-phonebook 20:F0:94:03:AB:DF --raw out.vcf

Books: pb (contacts), ich/och/mch/cch (calls), fav.
Locations: int (phone memory), sim1.

Needs contact sharing granted for this device in the phone's Bluetooth
settings, and obexd running: systemctl --user enable --now obex
"""

import sys
import argparse

from carlib.bluetooth import phonebook
from carlib.core.output import run, emit_json, CALL_GLYPH


def show_contacts(contacts) -> None:
    if not contacts:
        print('No entries returned.')
        return
    width = max((len(c.name) for c in contacts), default=10)
    for c in contacts:
        numbers = ', '.join(f'{n.number} ({n.type})'
                            for n in c.numbers) or '-'
        print(f'{c.name:<{width}}  {numbers}')
    print(f'\n{len(contacts)} contacts', file=sys.stderr)


def show_calls(contacts) -> None:
    if not contacts:
        print('No calls returned.')
        return
    width = max((len(c.name) for c in contacts), default=10)
    for c in contacts:
        glyph = CALL_GLYPH.get(c.call_type or '', ' ')
        name = c.name or '(unknown)'
        print(f'{glyph}  {c.call_time or "":<19}  {name:<{width}}  '
              f'{c.primary_number or "-"}')
    print(f'\n{len(contacts)} calls', file=sys.stderr)


async def main_async(args) -> None:
    if args.size:
        n = await phonebook.size(args.address, args.book, args.location)
        print(f'{args.book}@{args.location}: {n} entries')
        return

    if args.filters:
        for field in await phonebook.filter_fields(args.address):
            print(field)
        return

    contacts = await phonebook.fetch(
        args.address, args.book, args.location, args.raw)

    if args.json:
        emit_json(contacts)
    elif args.book in phonebook.CALL_BOOKS:
        show_calls(contacts)
    else:
        show_contacts(contacts)


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__.strip(),
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('address', help='phone MAC')
    ap.add_argument('--book', default='pb', choices=phonebook.BOOKS)
    ap.add_argument('--location', default='int',
                    choices=phonebook.LOCATIONS)
    ap.add_argument('--raw', metavar='FILE',
                    help='also keep the raw vCard data')
    ap.add_argument('--size', action='store_true',
                    help='just count entries')
    ap.add_argument('--filters', action='store_true',
                    help='list supported filter fields')
    ap.add_argument('--json', action='store_true')
    return run(main_async(ap.parse_args()))


if __name__ == '__main__':
    sys.exit(main())
