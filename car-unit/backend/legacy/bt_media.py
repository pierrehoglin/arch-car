#!/usr/bin/env python3
"""
Media control over Bluetooth AVRCP via BlueZ.

The phone must be connected with A2DP/AVRCP. BlueZ exposes an
org.bluez.MediaPlayer1 object under the device path once the phone has
an active media session -- start playback on the phone once if `players`
comes back empty.

Run:
    ./bt_media.py players                    # discover players
    ./bt_media.py status  20:F0:94:03:AB:DF
    ./bt_media.py play    20:F0:94:03:AB:DF
    ./bt_media.py pause   20:F0:94:03:AB:DF
    ./bt_media.py toggle  20:F0:94:03:AB:DF  # play/pause depending on state
    ./bt_media.py next    20:F0:94:03:AB:DF
    ./bt_media.py prev    20:F0:94:03:AB:DF
    ./bt_media.py monitor 20:F0:94:03:AB:DF  # live track changes
    ./bt_media.py waybar  20:F0:94:03:AB:DF  # JSON for a status bar

The player may be given as a MAC (either notation), an object path
fragment, or a substring of the device name.
"""

import sys
import json
import asyncio
import argparse

from sdbus import (
    sd_bus_open_system,
    set_default_bus,
    DbusInterfaceCommonAsync,
    DbusObjectManagerInterfaceAsync,
    dbus_method_async,
    dbus_property_async,
)

BUS_NAME = 'org.bluez'

STATUS_GLYPH = {
    'playing':      '\U000f040a',   # nf-md-play
    'paused':       '\U000f03e4',   # nf-md-pause
    'stopped':      '\U000f04db',   # nf-md-stop
    'forward-seek': '\U000f0211',
    'reverse-seek': '\U000f0214',
    'error':        '\U000f0026',
}


class MediaPlayer(DbusInterfaceCommonAsync,
                  interface_name='org.bluez.MediaPlayer1'):

    @dbus_method_async()
    async def play(self) -> None:
        raise NotImplementedError

    @dbus_method_async()
    async def pause(self) -> None:
        raise NotImplementedError

    @dbus_method_async()
    async def stop(self) -> None:
        raise NotImplementedError

    @dbus_method_async()
    async def next(self) -> None:
        raise NotImplementedError

    @dbus_method_async()
    async def previous(self) -> None:
        raise NotImplementedError

    @dbus_method_async()
    async def fast_forward(self) -> None:
        raise NotImplementedError

    @dbus_method_async()
    async def rewind(self) -> None:
        raise NotImplementedError

    @dbus_property_async(property_signature='s')
    def status(self) -> str:
        raise NotImplementedError

    @dbus_property_async(property_signature='u')
    def position(self) -> int:
        raise NotImplementedError

    @dbus_property_async(property_signature='a{sv}')
    def track(self) -> dict:
        raise NotImplementedError

    @dbus_property_async(property_signature='s')
    def repeat(self) -> str:
        raise NotImplementedError

    @dbus_property_async(property_signature='s')
    def shuffle(self) -> str:
        raise NotImplementedError


def unwrap(variant):
    if isinstance(variant, tuple) and len(variant) == 2:
        return variant[1]
    return variant


def props(raw: dict) -> dict:
    return {k: unwrap(v) for k, v in (raw or {}).items()}


def fmt_ms(ms) -> str:
    if not ms:
        return '0:00'
    total = int(ms) // 1000
    return f'{total // 60}:{total % 60:02d}'


async def list_players(bus) -> list[tuple[str, str, dict]]:
    """Return (player_path, device_name, player_props) for each player."""
    manager = DbusObjectManagerInterfaceAsync.new_proxy(BUS_NAME, '/', bus)
    objects = await manager.get_managed_objects()

    names = {}
    for path, interfaces in objects.items():
        dev = interfaces.get('org.bluez.Device1')
        if dev is not None:
            p = props(dev)
            names[path] = p.get('Alias') or p.get('Name') or path

    found = []
    for path, interfaces in objects.items():
        mp = interfaces.get('org.bluez.MediaPlayer1')
        if mp is None:
            continue
        device_path = path.rsplit('/', 1)[0]
        found.append((path, names.get(device_path, device_path), props(mp)))

    return found


async def resolve_player(bus, match: str) -> tuple[str, str]:
    """Find the player matching `match`. Returns (path, device_name)."""
    players = await list_players(bus)

    if not players:
        raise RuntimeError(
            'no media players; connect the phone with A2DP and start '
            'playback once so AVRCP registers a player')

    key = match.upper().replace(':', '_')
    hits = [(path, name) for path, name, _ in players
            if key in path.upper() or match.upper() in name.upper()]

    if not hits:
        known = ', '.join(name for _, name, _ in players)
        raise RuntimeError(f'no player matching {match!r}; have: {known}')
    if len(hits) > 1:
        raise RuntimeError(
            f'{match!r} is ambiguous: ' + ', '.join(n for _, n in hits))

    return hits[0]


async def snapshot(bus, path: str) -> dict:
    player = MediaPlayer.new_proxy(BUS_NAME, path, bus)

    try:
        status = await player.status
    except Exception:
        status = 'error'

    track = {}
    try:
        track = props(await player.track)
    except Exception:
        pass

    position = None
    try:
        position = await player.position
    except Exception:
        pass

    return {
        'status':   status,
        'title':    track.get('Title', ''),
        'artist':   track.get('Artist', ''),
        'album':    track.get('Album', ''),
        'duration': track.get('Duration'),
        'position': position,
        'track_no': track.get('TrackNumber'),
    }


# --- Commands --------------------------------------------------------------

async def cmd_players() -> None:
    bus = sd_bus_open_system()
    set_default_bus(bus)

    players = await list_players(bus)
    if not players:
        print('No media players.')
        print('Connect the phone with A2DP, then start playback once so '
              'AVRCP registers a player object.')
        return

    for path, name, p in players:
        glyph = STATUS_GLYPH.get(p.get('Status', ''), '')
        track = props(p.get('Track') or {})
        line = ' - '.join(x for x in (track.get('Artist'),
                                      track.get('Title')) if x)
        print(f"{name}  [{p.get('Status', '?')}] {glyph}")
        print(f"  path:  {path}")
        if line:
            print(f"  track: {line}")


async def cmd_status(sel: str) -> None:
    bus = sd_bus_open_system()
    set_default_bus(bus)

    path, name = await resolve_player(bus, sel)
    s = await snapshot(bus, path)

    glyph = STATUS_GLYPH.get(s['status'], '')
    print(f"{name}  {glyph} {s['status']}")
    if s['title']:
        print(f"  title:  {s['title']}")
    if s['artist']:
        print(f"  artist: {s['artist']}")
    if s['album']:
        print(f"  album:  {s['album']}")
    if s['duration']:
        print(f"  time:   {fmt_ms(s['position'])} / {fmt_ms(s['duration'])}")


async def cmd_control(sel: str, action: str) -> None:
    bus = sd_bus_open_system()
    set_default_bus(bus)

    path, name = await resolve_player(bus, sel)
    player = MediaPlayer.new_proxy(BUS_NAME, path, bus)

    if action == 'toggle':
        current = await player.status
        action = 'pause' if current == 'playing' else 'play'

    await {
        'play':     player.play,
        'pause':    player.pause,
        'stop':     player.stop,
        'next':     player.next,
        'prev':     player.previous,
        'forward':  player.fast_forward,
        'rewind':   player.rewind,
    }[action]()

    print(f'{action}: {name}')


async def cmd_monitor(sel: str) -> None:
    bus = sd_bus_open_system()
    set_default_bus(bus)

    path, name = await resolve_player(bus, sel)
    print(f'watching {name} (ctrl-c to stop)')

    s = await snapshot(bus, path)
    glyph = STATUS_GLYPH.get(s['status'], '')
    track = ' - '.join(x for x in (s['artist'], s['title']) if x)
    print(f"{glyph} {s['status']:<8} {track}")

    watcher = MediaPlayer.new_proxy(BUS_NAME, path, bus)
    async for iface, changed, _invalidated in watcher.properties_changed:
        if iface != 'org.bluez.MediaPlayer1':
            continue
        c = props(changed)

        if 'Track' in c:
            t = props(c['Track'])
            line = ' - '.join(x for x in (t.get('Artist'),
                                          t.get('Title')) if x)
            print(f"  track: {line}")
        if 'Status' in c:
            st = c['Status']
            print(f"  {STATUS_GLYPH.get(st, '')} {st}")


async def cmd_waybar(sel: str) -> None:
    """Single JSON line for a Waybar custom module."""
    bus = sd_bus_open_system()
    set_default_bus(bus)

    try:
        path, name = await resolve_player(bus, sel)
        s = await snapshot(bus, path)
    except Exception:
        print(json.dumps({'text': '', 'class': 'disconnected'}))
        return

    glyph = STATUS_GLYPH.get(s['status'], '')
    track = ' - '.join(x for x in (s['artist'], s['title']) if x)
    text = f"{glyph}  {track}" if track else glyph

    print(json.dumps({
        'text': text,
        'alt': s['status'],
        'class': s['status'],
        'tooltip': f"{s['title']}\n{s['artist']}\n{s['album']}".strip(),
    }, ensure_ascii=False))


# --- Entry point -----------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(
        description='Media control over Bluetooth AVRCP via BlueZ.')
    sub = ap.add_subparsers(dest='cmd', required=True)

    sub.add_parser('players', help='list media players')

    def with_player(name: str, help_text: str):
        p = sub.add_parser(name, help=help_text)
        p.add_argument('player', metavar='MAC|NAME',
                       help='MAC, path fragment or device name')
        return p

    with_player('status', 'show what is playing')
    with_player('play', 'resume playback')
    with_player('pause', 'pause playback')
    with_player('stop', 'stop playback')
    with_player('toggle', 'play or pause depending on state')
    with_player('next', 'next track')
    with_player('prev', 'previous track')
    with_player('forward', 'fast forward')
    with_player('rewind', 'rewind')
    with_player('monitor', 'watch track and status changes')
    with_player('waybar', 'emit one JSON line for a status bar')

    args = ap.parse_args()

    controls = {'play', 'pause', 'stop', 'toggle', 'next', 'prev',
                'forward', 'rewind'}

    try:
        if args.cmd == 'players':
            asyncio.run(cmd_players())
        elif args.cmd == 'status':
            asyncio.run(cmd_status(args.player))
        elif args.cmd == 'monitor':
            asyncio.run(cmd_monitor(args.player))
        elif args.cmd == 'waybar':
            asyncio.run(cmd_waybar(args.player))
        elif args.cmd in controls:
            asyncio.run(cmd_control(args.player, args.cmd))
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        print(f'error: {exc}', file=sys.stderr)
        return 1

    return 0


if __name__ == '__main__':
    sys.exit(main())
