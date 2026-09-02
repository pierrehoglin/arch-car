#!/usr/bin/env python3
"""
Named locations.

    places                      # list them
    places save home            # saves the current GPS position
    places save work --latitude 59.3293 --longitude 18.0686
    places show home
    places forget work
    places here                 # where we are now

Saved once, usable by anything -- the weather command takes a place
name, and a future map or geofence would use the same list.

"here" is reserved for the GPS position. To pin it, useful on a bench
with no sky view:

    settings set location.latitude 62.3874
    settings set location.longitude 17.3116
"""

import sys
import argparse

from carlib.location import places
from carlib.core.output import run, emit_json, global_flags, parse_args


def show(place) -> None:
    print(place.name)
    print(f'  {place.latitude:.4f}, {place.longitude:.4f}')
    if place.altitude is not None:
        print(f'  {place.altitude:.0f} m')
    print(f'  https://www.openstreetmap.org/'
          f'?mlat={place.latitude}&mlon={place.longitude}#map=14')


async def cmd_list(args) -> None:
    saved = places.saved()
    if args.json:
        emit_json(saved)
        return

    if not saved:
        print('no saved places')
        print('add one with: places save home', file=sys.stderr)
        return

    width = max(len(p.name) for p in saved)
    for place in saved:
        alt = f'  {place.altitude:>5.0f} m' if place.altitude else ''
        print(f'  {place.name:<{width}}  {place.latitude:>9.4f}, '
              f'{place.longitude:>9.4f}{alt}')


async def cmd_save(args) -> None:
    if args.latitude is not None and args.longitude is not None:
        lat, lon, alt = args.latitude, args.longitude, args.altitude
    else:
        # No coordinates, so save where we are.
        current = await places.here()
        lat, lon, alt = (current.latitude, current.longitude,
                         current.altitude)

    places.save(args.name, lat, lon, alt)
    print(f'saved {args.name}: {lat:.4f}, {lon:.4f}')


async def cmd_forget(args) -> None:
    places.remove(args.name)
    print(f'removed {args.name}')


async def cmd_show(args) -> None:
    place = await places.resolve(args.name)
    if args.json:
        emit_json(place)
    else:
        show(place)


async def cmd_here(args) -> None:
    place = await places.here()
    if args.json:
        emit_json(place)
    else:
        show(place)


def main() -> int:
    common = global_flags('--json')

    ap = argparse.ArgumentParser(
        description=__doc__.strip(),
        parents=[common],
        formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd')

    p = sub.add_parser('list', parents=[common], help='saved places')
    p.set_defaults(fn=cmd_list)

    p = sub.add_parser('here', parents=[common],
                       help='where we are now')
    p.set_defaults(fn=cmd_here)

    p = sub.add_parser('show', parents=[common],
                       help='one place in detail')
    p.set_defaults(fn=cmd_show)
    p.add_argument('name', nargs='?', default=None,
                   help='a saved place, or omit for here')

    p = sub.add_parser('save', parents=[common],
                       help='save a place, here by default')
    p.set_defaults(fn=cmd_save)
    p.add_argument('name')
    p.add_argument('--latitude', type=float)
    p.add_argument('--longitude', type=float)
    p.add_argument('--altitude', type=float)

    p = sub.add_parser('forget', parents=[common],
                       help='remove a saved place')
    p.set_defaults(fn=cmd_forget)
    p.add_argument('name')

    args = parse_args(ap, 'list', defaults={'json': False})
    return run(args.fn(args))


if __name__ == '__main__':
    sys.exit(main())
