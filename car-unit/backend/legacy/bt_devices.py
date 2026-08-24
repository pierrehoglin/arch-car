#!/usr/bin/env python3
"""
List BlueZ devices with their name, icon and connection state.

Install:
    sudo pacman -S python-sdbus
    # or in a venv: pip install sdbus

Run:
    ./bt_devices.py            # table output
    ./bt_devices.py --json     # JSON, e.g. for a Waybar module
"""

import sys
import json
import asyncio

from sdbus import (
    sd_bus_open_system,
    set_default_bus,
    DbusObjectManagerInterfaceAsync,
)


# BlueZ reports a freedesktop icon name in the Icon property, but not every
# device sets it. Map to Nerd Font glyphs, falling back on the device Class.
ICONS = {
    'audio-card':            '\U000f075a',   # nf-md-speaker
    'audio-headset':         '\U000f02cb',   # nf-md-headset
    'audio-headphones':      '\U000f02cb',
    'camera-photo':          '\U000f0100',   # nf-md-camera
    'camera-video':          '\U000f0567',   # nf-md-video
    'computer':              '\U000f0379',   # nf-md-laptop
    'input-gaming':          '\U000f0eb5',   # nf-md-controller
    'input-keyboard':        '\U000f030c',   # nf-md-keyboard
    'input-mouse':           '\U000f037d',   # nf-md-mouse
    'input-tablet':          '\U000f04f6',   # nf-md-tablet
    'phone':                 '\U000f011c',   # nf-md-cellphone
    'printer':               '\U000f042a',   # nf-md-printer
    'scanner':               '\U000f04ba',   # nf-md-scanner
    'video-display':         '\U000f0379',
    'multimedia-player':     '\U000f075a',
}
DEFAULT_ICON = '\U000f00af'                  # nf-md-bluetooth

PLAY_GLYPH = {
    'playing': '\U000f040a',   # nf-md-play
    'paused':  '\U000f03e4',   # nf-md-pause
    'stopped': '\U000f04db',   # nf-md-stop
}


def unwrap(variant):
    """sdbus returns properties as (signature, value) tuples."""
    if isinstance(variant, tuple) and len(variant) == 2:
        return variant[1]
    return variant


async def collect_devices() -> list[dict]:
    bus = sd_bus_open_system()
    set_default_bus(bus)

    manager = DbusObjectManagerInterfaceAsync.new_proxy('org.bluez', '/', bus)
    objects = await manager.get_managed_objects()

    devices = []
    players = {}      # device path prefix -> MediaPlayer1 properties

    # MediaPlayer1 objects live under the device path, e.g.
    # /org/bluez/hci0/dev_AA_../player0, so index them by prefix first.
    for path, interfaces in objects.items():
        mp = interfaces.get('org.bluez.MediaPlayer1')
        if mp is not None:
            players[path.rsplit('/', 1)[0]] = mp

    for path, interfaces in objects.items():
        props = interfaces.get('org.bluez.Device1')
        if props is None:
            continue

        icon_name = unwrap(props.get('Icon', ('s', '')))

        battery = None
        bat_iface = interfaces.get('org.bluez.Battery1')
        if bat_iface is not None:
            battery = unwrap(bat_iface.get('Percentage', ('y', None)))

        media = None
        mp = players.get(path)
        if mp is not None:
            track = unwrap(mp.get('Track', ('a{sv}', {}))) or {}
            media = {
                'status': unwrap(mp.get('Status', ('s', ''))),
                'title':  unwrap(track.get('Title', ('s', ''))),
                'artist': unwrap(track.get('Artist', ('s', ''))),
                'album':  unwrap(track.get('Album', ('s', ''))),
            }

        devices.append({
            'path':      path,
            'address':   unwrap(props.get('Address', ('s', ''))),
            'name':      unwrap(props.get('Alias',
                         props.get('Name', ('s', '(unnamed)')))),
            'icon_name': icon_name,
            'icon':      ICONS.get(icon_name, DEFAULT_ICON),
            'connected': bool(unwrap(props.get('Connected', ('b', False)))),
            'paired':    bool(unwrap(props.get('Paired', ('b', False)))),
            'trusted':   bool(unwrap(props.get('Trusted', ('b', False)))),
            'rssi':      unwrap(props.get('RSSI', ('n', None))),
            'battery':   battery,
            'media':     media,
        })

    # Connected first, then paired, then by name.
    devices.sort(key=lambda d: (not d['connected'], not d['paired'],
                                d['name'].lower()))
    return devices


def print_table(devices: list[dict]) -> None:
    if not devices:
        print('No devices known to BlueZ.')
        return

    width = max(len(d['name']) for d in devices)
    for d in devices:
        state = 'connected' if d['connected'] else \
                'paired' if d['paired'] else '-'
        rssi = f"{d['rssi']:>4} dBm" if d['rssi'] is not None else '        '
        bat = f"{d['battery']:>3}%" if d['battery'] is not None else '    '
        print(f"{d['icon']}  {d['name']:<{width}}  {d['address']}  "
              f"{state:<9}  {rssi}  {bat}  {d['icon_name']}")

        m = d.get('media')
        if m and (m['title'] or m['artist']):
            glyph = PLAY_GLYPH.get(m['status'], '')
            track = ' - '.join(p for p in (m['artist'], m['title']) if p)
            print(f"   {glyph}  {track}")


def main() -> int:
    try:
        devices = asyncio.run(collect_devices())
    except Exception as exc:
        print(f'error: {exc}', file=sys.stderr)
        return 1

    if '--json' in sys.argv:
        print(json.dumps(devices, indent=2))
    else:
        print_table(devices)
    return 0


if __name__ == '__main__':
    sys.exit(main())
