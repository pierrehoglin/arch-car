#!/usr/bin/env python3
"""
Paired Bluetooth devices: state, battery, capabilities, now-playing.

    ./bt-devices
    ./bt-devices --json
    ./bt-devices --connected
"""

import sys
import argparse

from carlib.dbus import bluez
from carlib.core.output import (run, emit_json, DEVICE_ICONS, GLYPH,
                                STATUS_GLYPH)


def show(devices) -> None:
    if not devices:
        print('No devices known to BlueZ.')
        return

    width = max(len(d.name) for d in devices)

    for d in devices:
        icon = DEVICE_ICONS.get(d.icon, GLYPH['bluetooth'])
        state = ('connected' if d.connected
                 else 'paired' if d.paired else '-')
        rssi = f'{d.rssi:>4} dBm' if d.rssi is not None else ' ' * 8
        bat = f'{d.battery:>3}%' if d.battery is not None else '    '

        caps = ''.join([
            'H' if d.supports_hfp else '-',
            'P' if d.supports_pbap else '-',
            'M' if d.supports_map else '-',
        ])

        print(f'{icon}  {d.name:<{width}}  {d.address}  '
              f'{state:<9}  {rssi}  {bat}  {caps}')

        if d.player and (d.player.track.title or d.player.track.artist):
            glyph = STATUS_GLYPH.get(d.player.status, '')
            print(f'   {glyph}  {d.player.track.label}')

    print('\ncapabilities: H=handsfree  P=phonebook  M=messages',
          file=sys.stderr)


async def main_async(args) -> None:
    devices = await bluez.inventory()
    if args.connected:
        devices = [d for d in devices if d.connected]

    if args.json:
        emit_json(devices)
    else:
        show(devices)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.strip())
    ap.add_argument('--json', action='store_true')
    ap.add_argument('--connected', action='store_true',
                    help='only currently connected devices')
    return run(main_async(ap.parse_args()))


if __name__ == '__main__':
    sys.exit(main())
