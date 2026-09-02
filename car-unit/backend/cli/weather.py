#!/usr/bin/env python3
"""
Weather.

    weather                     # here, now and the next few hours
    weather home                # a saved place
    weather now
    weather hourly home --hours 24
    weather --refresh           # ignore the cache
    weather providers
    weather waybar

Location comes from GPS unless a place is named. Places are managed by
the `places` command and shared with anything else that needs one:

    places save home
    weather home

Each place caches separately, so checking the weather at home while
driving does not evict the local forecast.

Providers are selectable:

    settings set weather.provider metno

Most services ask you to identify yourself, and MET Norway blocks
requests that do not:

    settings set weather.contact you@example.com
"""

import sys
import json
import argparse

from carlib.location import places
from carlib.weather import service
from carlib.core.output import run, emit_json, global_flags, parse_args


def show_now(conditions, forecast) -> None:
    c = conditions
    print(f'{c.glyph}  {c.summary}')
    print()
    if c.feels_like is not None:
        print(f'  feels like:  {c.feels_like:.0f}\u00b0C')
    if c.humidity is not None:
        print(f'  humidity:    {c.humidity:.0f}%')
    if c.pressure is not None:
        print(f'  pressure:    {c.pressure:.0f} hPa')
    if c.wind_speed is not None:
        gust = (f'  gusting {c.wind_gust:.0f}'
                if c.wind_gust is not None else '')
        print(f'  wind:        {c.wind_speed:.1f} m/s '
              f'{c.wind_compass} {c.wind_arrow}{gust}')
    if c.cloud_cover is not None:
        print(f'  cloud:       {c.cloud_cover:.0f}%')
    if c.precipitation is not None:
        prob = (f'  ({c.precipitation_probability:.0f}% chance)'
                if c.precipitation_probability is not None else '')
        print(f'  rain:        {c.precipitation:.1f} mm '
              f'over {c.period_hours}h{prob}')
    if c.uv_index is not None:
        print(f'  uv:          {c.uv_index:.1f}')

    print()
    where = '  '
    if forecast.place and forecast.place != places.HERE:
        where += f'{forecast.place}  '
    where += f'{forecast.latitude:.4f}, {forecast.longitude:.4f}'
    if forecast.altitude:
        where += f' at {forecast.altitude:.0f} m'
    print(where)

    via = f'  via {forecast.provider}'
    if forecast.updated:
        via += f', updated {forecast.updated:%H:%M}'
    print(via)

    if forecast.stale:
        print('\n  (cached forecast has expired; --refresh to update)',
              file=sys.stderr)


def show_hourly(entries) -> None:
    if not entries:
        print('no forecast data')
        return

    for e in entries:
        when = f'{e.time:%a %H:%M}' if e.time else '?'
        temp = (f'{e.temperature:>5.1f}\u00b0'
                if e.temperature is not None else '     ')
        wind = (f'{e.wind_speed:>4.1f} m/s {e.wind_compass:<2}'
                if e.wind_speed is not None else '')
        rain = (f'{e.precipitation:>5.1f} mm'
                if e.precipitation else '         ')
        print(f'  {when:<12} {e.glyph}  {temp}  {rain}  {wind}')


async def cmd_now(args) -> None:
    forecast = await service.forecast(args.place, refresh=args.refresh)
    if args.json:
        emit_json(forecast.current)
        return
    if forecast.current is None:
        print('no current conditions in the forecast')
        return
    show_now(forecast.current, forecast)


async def cmd_hourly(args) -> None:
    forecast = await service.forecast(args.place, refresh=args.refresh)
    entries = forecast.next_hours(args.hours)
    if args.json:
        emit_json(entries)
        return
    show_hourly(entries)


async def cmd_full(args) -> None:
    forecast = await service.forecast(args.place, refresh=args.refresh)
    if args.json:
        emit_json(forecast)
        return
    if forecast.current is not None:
        show_now(forecast.current, forecast)
        print()
    show_hourly(forecast.next_hours(args.hours))


async def cmd_providers(args) -> None:
    rows = service.providers()
    if args.json:
        emit_json(rows)
        return
    for row in rows:
        mark = '*' if row['active'] else ' '
        scope = 'global' if row['global'] else 'regional'
        print(f'{mark} {row["name"]:<12} {scope:<9} {row["description"]}')
    print('\n* active   change with: settings set weather.provider NAME',
          file=sys.stderr)


async def cmd_waybar(args) -> None:
    """One JSON line for a Waybar custom module."""
    try:
        forecast = await service.forecast(args.place)
        c = forecast.current
    except Exception as exc:
        print(json.dumps({
            'text': '',
            'alt': 'unavailable',
            'class': 'unavailable',
            'tooltip': str(exc).splitlines()[0],
        }, ensure_ascii=False))
        return

    if c is None:
        print(json.dumps({'text': '', 'class': 'unavailable',
                          'tooltip': 'no data'}, ensure_ascii=False))
        return

    temp = (f'{c.temperature:.0f}\u00b0'
            if c.temperature is not None else '')

    lines = [c.summary]
    for entry in forecast.next_hours(6)[1:]:
        when = f'{entry.time:%H:%M}' if entry.time else ''
        lines.append(f'{when}  {entry.glyph}  '
                     f'{entry.temperature:.0f}\u00b0'
                     if entry.temperature is not None else when)

    print(json.dumps({
        'text': f'{c.glyph}  {temp}',
        'alt': str(c.condition),
        'class': str(c.condition),
        'tooltip': '\n'.join(lines),
    }, ensure_ascii=False))


def main() -> int:
    common = global_flags('--json', '--refresh')

    ap = argparse.ArgumentParser(
        description=__doc__.strip(),
        parents=[common],
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--hours', type=int, default=12,
                    help='how far ahead to show (default 12)')
    sub = ap.add_subparsers(dest='cmd')

    for name, fn, help_text in (
            ('now', cmd_now, 'current conditions'),
            ('hourly', cmd_hourly, 'the next few hours'),
            ('full', cmd_full, 'conditions and forecast'),
            ('waybar', cmd_waybar, 'one JSON line for a status bar')):
        sp = sub.add_parser(name, parents=[common], help=help_text)
        sp.set_defaults(fn=fn)
        sp.add_argument('place', nargs='?', default=None)
        sp.add_argument('--hours', type=int, default=12)

    p = sub.add_parser('providers', parents=[common],
                       help='what services are available')
    p.set_defaults(fn=cmd_providers)

    # `weather home` should mean `weather full home`, but a bare
    # positional at the top level would swallow the subcommand name --
    # `weather save home` would read "save" as the place. So insert
    # the default subcommand only when the first argument is not one.
    argv = sys.argv[1:]
    commands = set(sub.choices)
    leading = next((a for a in argv if not a.startswith('-')), None)
    if leading is not None and leading not in commands:
        index = argv.index(leading)
        argv = argv[:index] + ['full'] + argv[index:]

    args = parse_args(ap, 'full', argv=argv,
                      defaults={'json': False, 'refresh': False,
                                'hours': 12, 'place': None})
    return run(args.fn(args))


if __name__ == '__main__':
    sys.exit(main())
