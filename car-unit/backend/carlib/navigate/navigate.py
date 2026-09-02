#!/usr/bin/env python3
"""
Routing.

    navigate to "Slottsskogen"          # from where we are
    navigate to home
    navigate from work to home
    navigate to 57.6889,11.9439
    navigate status                     # is the router reachable

Destinations can be a saved place, a coordinate pair, or anything the
geocoder can find.

Routes come from Valhalla. The default is the public FOSSGIS server,
which is free and carries the whole planet but allows one call per
second. For rerouting that works without signal -- which is when you
need it -- run your own and point at it:

    settings set navigation.url http://localhost:8002
"""

import sys
import argparse

from carlib.location import geocoding, places
from carlib.navigation import routing
from carlib.core.errors import NotFoundError
from carlib.core.output import run, emit_json, global_flags, parse_args


def show(route) -> None:
    print(route.label)
    if route.summary:
        print(f'  {route.summary}')
    print()

    for maneuver in route.maneuvers:
        if maneuver.distance:
            distance = maneuver.distance_metres
            near = (f'{distance:>5.0f} m' if distance < 1000
                    else f'{distance / 1000:>4.1f} km')
        else:
            near = '      '
        print(f'  {near}  {maneuver.instruction or maneuver.label}')


async def resolve(text: str):
    """
    Turn what someone typed into a coordinate pair.

    Tries a saved place first, then a literal coordinate pair, then
    the geocoder -- cheapest and most certain first, so "home" never
    costs a network call.
    """
    text = str(text).strip()

    place = places.find(text)
    if place is not None:
        return place.latitude, place.longitude, place.name

    if ',' in text:
        left, _, right = text.partition(',')
        try:
            return float(left), float(right), text
        except ValueError:
            pass

    found = await geocoding.search(text, limit=1)
    if not found:
        raise NotFoundError('destination', text,
                            ['try a saved place, "lat,lon", or a '
                             'more specific address'])
    return found[0].latitude, found[0].longitude, found[0].short


async def cmd_to(args) -> None:
    """Route from somewhere to somewhere. Origin defaults to here."""
    destination = await resolve(args.destination)

    if args.origin:
        origin = await resolve(args.origin)
    else:
        here = await places.here()
        origin = (here.latitude, here.longitude,
                  here.address or 'here')

    route = await routing.route(
        [(origin[0], origin[1]), (destination[0], destination[1])],
        costing=args.costing)

    if args.json:
        emit_json(route)
        return

    print(f'{origin[2]}  ->  {destination[2]}')
    print()
    show(route)
    print(f'\n{geocoding.ATTRIBUTION}', file=sys.stderr)


async def cmd_status(args) -> None:
    info = await routing.status()
    if args.json:
        emit_json(info)
        return

    print(info['url'])
    if info.get('version'):
        print(f'  Valhalla {info["version"]}')
    if info.get('tileset_last_modified'):
        print(f'  tiles from {info["tileset_last_modified"]}')
    print(f'  {"public server" if info["public"] else "local instance"}')

    if info['public']:
        print('\none call per second, and it needs a network. '
              'A local instance\nreroutes without signal.',
              file=sys.stderr)


def main() -> int:
    common = global_flags('--json')

    ap = argparse.ArgumentParser(
        description=__doc__.strip(),
        parents=[common],
        formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd')

    p = sub.add_parser('to', parents=[common],
                       help='route to a destination')
    p.set_defaults(fn=cmd_to)
    p.add_argument('destination')
    p.add_argument('--from', dest='origin', default='',
                   help='start somewhere other than here')
    p.add_argument('--costing', default=None,
                   choices=routing.COSTINGS)

    p = sub.add_parser('from', parents=[common],
                       help='route between two places')
    p.set_defaults(fn=cmd_to)
    p.add_argument('origin')
    p.add_argument('destination')
    p.add_argument('--costing', default=None,
                   choices=routing.COSTINGS)

    p = sub.add_parser('status', parents=[common],
                       help='is the router reachable')
    p.set_defaults(fn=cmd_status)

    argv = sys.argv[1:]

    # `navigate from work to home` reads better than requiring the
    # positional order, so drop the "to" that separates them.
    if argv and argv[0] == 'from' and 'to' in argv:
        argv = [a for i, a in enumerate(argv) if not (i > 0 and a == 'to')]

    args = parse_args(ap, 'status', argv=argv,
                      defaults={'json': False})
    return run(args.fn(args))


if __name__ == '__main__':
    sys.exit(main())
