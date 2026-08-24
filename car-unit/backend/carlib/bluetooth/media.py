"""
AVRCP playback control.

The MediaPlayer1 object only exists once the phone has an active media
session -- if `players()` is empty, start playback on the phone once.
"""

from typing import AsyncIterator

from carlib.dbus import bluez
from carlib.dbus.bluez import Player, Track
from carlib.core.match import select_optional
from carlib.dbus.variants import props

ACTIONS = ('play', 'pause', 'stop', 'next', 'prev', 'forward', 'rewind')


async def players() -> list[Player]:
    return await bluez.players()


async def resolve(match: str | None = None) -> Player:
    """Pick a player by MAC, path fragment or device name."""
    return select_optional(
        await players(), match,
        what='player',
        keys=lambda p: (p.path, p.device_path, p.device_name),
        label=lambda p: p.device_name,
    )


async def status(match: str | None = None) -> Player:
    """
    Current state, re-read live rather than from the cached inventory.

    Position in particular is stale the moment you fetch it.
    """
    player = await resolve(match)
    proxy = bluez.player_proxy(player.path)

    try:
        player.status = await proxy.status
    except Exception:
        player.status = 'error'

    try:
        player.track = Track.from_props(await proxy.track)
    except Exception:
        pass

    try:
        player.position = await proxy.position
    except Exception:
        player.position = None

    return player


async def control(action: str, match: str | None = None) -> Player:
    """
    Apply a transport action. Returns the player it acted on.

    'toggle' reads the current status and flips it.
    """
    player = await resolve(match)
    proxy = bluez.player_proxy(player.path)

    if action == 'toggle':
        current = await proxy.status
        action = 'pause' if current == 'playing' else 'play'

    methods = {
        'play': proxy.play,
        'pause': proxy.pause,
        'stop': proxy.stop,
        'next': proxy.next,
        'prev': proxy.previous,
        'forward': proxy.fast_forward,
        'rewind': proxy.rewind,
    }
    if action not in methods:
        raise ValueError(f'unknown action {action!r}')

    await methods[action]()
    player.status = action
    return player


async def watch(match: str | None = None
                ) -> AsyncIterator[tuple[str, dict]]:
    """
    Yield (kind, data) as playback changes, where kind is 'track' or
    'status'.

    Pushes rather than polls -- this is what a UI should consume.

        async for kind, data in media.watch():
            ...
    """
    player = await resolve(match)
    proxy = bluez.player_proxy(player.path)

    async for iface, changed, _invalidated in proxy.properties_changed:
        if iface != bluez.IFACE_PLAYER:
            continue
        c = props(changed)

        if 'Track' in c:
            yield 'track', Track.from_props(c['Track']).__dict__
        if 'Status' in c:
            yield 'status', {'status': c['Status']}
        if 'Position' in c:
            yield 'position', {'position': c['Position']}


def format_ms(ms: int | None) -> str:
    """Milliseconds as m:ss, for display."""
    if not ms:
        return '0:00'
    total = int(ms) // 1000
    return f'{total // 60}:{total % 60:02d}'
