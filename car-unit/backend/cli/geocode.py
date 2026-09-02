#!/usr/bin/env python3
"""
Address search and lookup.

    geocode search "Kungsgatan 12 Stockholm"
    geocode search "Ullevi" --limit 3
    geocode search "Berlin" --anywhere
    geocode reverse                     # where we are now
    geocode reverse 59.3293 18.0686
    geocode here                        # our address, from the cache

Results can be saved as places, which the weather command and
anything else can then use by name:

    geocode search "Slottsskogen" --save park
    weather park

Uses Nominatim, the OpenStreetMap geocoder. It runs on donated
servers with limited capacity, so its usage policy is binding:

    https://operations.osmfoundation.org/policies/nominatim/

In short: at most one request per second, a User-Agent that
identifies this application, results cached, and attribution shown.
Anything run at regular intervals is held to four requests a minute.
Set your contact so requests can be attributed:

    settings set contact you@example.com

Searches are limited to one country, Sweden by default:

    settings set geocoding.country se

Automatic address updates while driving are gated on distance moved
rather than time, so a parked car makes no requests. Adjust with:

    settings set geocoding.move_metres 1000
"""

import sys
import argparse

from carlib.location import geocoding, places
from carlib.core.output import run, emit_json, global_flags, parse_args


def show(address) -> None:
    print(address.short)
    print()
    if address.display_name:
        print(f'  {address.display_name}')
    print(f'  {address.latitude:.5f}, {address.longitude:.5f}')
    if address.postcode:
        print(f'  postcode {address.postcode}')
    if address.kind:
        kind = f'{address.category}/{address.kind}'.strip('/')
        print(f'  {kind}')
    print(f'  https://www.openstreetmap.org/'
          f'?mlat={address.latitude}&mlon={address.longitude}#map=17')


def show_list(results) -> None:
    for index, address in enumerate(results, 1):
        print(f'{index}. {address.short}')
        print(f'   {address.display_name}')
        print(f'   {address.latitude:.5f}, {address.longitude:.5f}')


def attribution() -> None:
    """
    Required by the Nominatim usage policy and the ODbL licence.

    On stderr so it does not corrupt piped output, but still visible
    to anyone using the command.
    """
    print(f'\n{geocoding.ATTRIBUTION}', file=sys.stderr)


async def cmd_search(args) -> None:
    # Resolve the country here rather than leaving it None, so the
    # empty-result hint can say where it actually looked.
    if args.anywhere:
        country = ''
    elif args.country is not None:
        country = args.country
    else:
        country = geocoding.default_country()

    results = await geocoding.search(args.query, limit=args.limit,
                                     country=country)

    if args.json:
        emit_json(results)
        return

    if not results:
        print('nothing found')
        if country:
            print(f'searched {country.upper()} only -- try --anywhere, '
                  f'or --country XX', file=sys.stderr)
        else:
            print('searched worldwide; try a more specific query',
                  file=sys.stderr)
        return

    show_list(results)

    if args.save:
        best = results[0]
        # The address is already known, so no second lookup.
        await places.save(args.save, best.latitude, best.longitude,
                          address=best.short)
        print(f'\nsaved "{args.save}": {best.short}')

    attribution()


async def cmd_reverse(args) -> None:
    if args.latitude is not None and args.longitude is not None:
        latitude, longitude = args.latitude, args.longitude
    else:
        here = await places.here()
        latitude, longitude = here.latitude, here.longitude

    address = await geocoding.reverse(latitude, longitude,
                                      use_cache=not args.refresh)

    if args.json:
        emit_json(address)
        return

    show(address)

    if args.save:
        await places.save(args.save, address.latitude,
                          address.longitude, address=address.short)
        print(f'\nsaved "{args.save}"')

    attribution()


async def cmd_here(args) -> None:
    """
    The address last looked up for our own position.

    Read from the cache rather than querying, so this is free to call
    as often as a status bar likes.
    """
    address = geocoding.current()

    if args.json:
        emit_json(address)
        return

    if address is None:
        print('no address known yet')
        print('the daemon updates this as the car moves; '
              '`geocode reverse` looks it up now', file=sys.stderr)
        return

    show(address)
    attribution()


async def cmd_waybar(args) -> None:
    """One JSON line for a status bar. Never queries."""
    import json

    address = geocoding.current()
    text = address.short if address else ''

    print(json.dumps({
        'text': text,
        'alt': 'known' if address else 'unknown',
        'class': 'known' if address else 'unknown',
        'tooltip': (address.display_name if address
                    else 'no address known yet'),
    }, ensure_ascii=False))


def main() -> int:
    common = global_flags('--json')

    ap = argparse.ArgumentParser(
        description=__doc__.strip(),
        parents=[common],
        formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd')

    p = sub.add_parser('search', parents=[common],
                       help='find a place by name or address')
    p.set_defaults(fn=cmd_search)
    p.add_argument('query')
    p.add_argument('--limit', type=int, default=5)
    p.add_argument('--country', default=None,
                   help='restrict to a country code; defaults to the '
                        'geocoding.country setting')
    p.add_argument('--anywhere', action='store_true',
                   help='search worldwide, ignoring the country '
                        'setting')
    p.add_argument('--save', default='',
                   help='save the first result as a named place')

    p = sub.add_parser('reverse', parents=[common],
                       help='the address at a point, or here')
    p.set_defaults(fn=cmd_reverse)
    p.add_argument('latitude', nargs='?', type=float)
    p.add_argument('longitude', nargs='?', type=float)
    p.add_argument('--refresh', action='store_true',
                   help='ignore the cache')
    p.add_argument('--save', default='',
                   help='save the result as a named place')

    p = sub.add_parser('here', parents=[common],
                       help='our current address, from the cache')
    p.set_defaults(fn=cmd_here)

    p = sub.add_parser('waybar', parents=[common],
                       help='one JSON line for a status bar')
    p.set_defaults(fn=cmd_waybar)

    args = parse_args(ap, 'here', defaults={'json': False})
    return run(args.fn(args))


if __name__ == '__main__':
    sys.exit(main())
