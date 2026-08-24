"""
BlueZ: devices, battery, media players.

Interface declarations plus the queries that read them. BlueZ has no
"list devices" call -- you fetch every managed object and filter, which
is what `inventory()` does in one round trip.
"""

from dataclasses import dataclass, field, asdict
from typing import Any

from sdbus import (
    DbusInterfaceCommonAsync,
    DbusObjectManagerInterfaceAsync,
    dbus_method_async,
    dbus_property_async,
)

from carlib.dbus.connection import system_bus
from carlib.dbus.variants import props

SERVICE = 'org.bluez'

IFACE_DEVICE = 'org.bluez.Device1'
IFACE_BATTERY = 'org.bluez.Battery1'
IFACE_PLAYER = 'org.bluez.MediaPlayer1'
IFACE_ADAPTER = 'org.bluez.Adapter1'


# --- Interfaces ------------------------------------------------------------

class Adapter1(DbusInterfaceCommonAsync,
               interface_name=IFACE_ADAPTER):

    @dbus_property_async(property_signature='b')
    def powered(self) -> bool:
        raise NotImplementedError

    @dbus_property_async(property_signature='b')
    def discovering(self) -> bool:
        raise NotImplementedError

    @dbus_property_async(property_signature='b')
    def discoverable(self) -> bool:
        raise NotImplementedError

    @dbus_property_async(property_signature='u')
    def discoverable_timeout(self) -> int:
        raise NotImplementedError

    @dbus_property_async(property_signature='b')
    def pairable(self) -> bool:
        raise NotImplementedError

    @dbus_property_async(property_signature='u')
    def pairable_timeout(self) -> int:
        raise NotImplementedError

    @dbus_property_async(property_signature='s')
    def alias(self) -> str:
        raise NotImplementedError

    @dbus_property_async(property_signature='s')
    def address(self) -> str:
        raise NotImplementedError

    @dbus_method_async()
    async def start_discovery(self) -> None:
        raise NotImplementedError

    @dbus_method_async()
    async def stop_discovery(self) -> None:
        raise NotImplementedError

    @dbus_method_async(input_signature='o')
    async def remove_device(self, device: str) -> None:
        raise NotImplementedError


class Device1(DbusInterfaceCommonAsync,
              interface_name=IFACE_DEVICE):

    @dbus_method_async()
    async def connect(self) -> None:
        raise NotImplementedError

    @dbus_method_async()
    async def disconnect(self) -> None:
        raise NotImplementedError

    @dbus_property_async(property_signature='b')
    def connected(self) -> bool:
        raise NotImplementedError


class MediaPlayer1(DbusInterfaceCommonAsync,
                   interface_name=IFACE_PLAYER):

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


# --- Data ------------------------------------------------------------------

@dataclass
class Track:
    title: str = ''
    artist: str = ''
    album: str = ''
    duration: int | None = None
    track_number: int | None = None

    @classmethod
    def from_props(cls, raw: dict | None) -> 'Track':
        p = props(raw)
        return cls(
            title=p.get('Title', ''),
            artist=p.get('Artist', ''),
            album=p.get('Album', ''),
            duration=p.get('Duration'),
            track_number=p.get('TrackNumber'),
        )

    @property
    def label(self) -> str:
        return ' - '.join(x for x in (self.artist, self.title) if x)


@dataclass
class Player:
    path: str
    device_path: str
    device_name: str
    status: str = ''
    position: int | None = None
    track: Track = field(default_factory=Track)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Device:
    path: str
    address: str
    name: str
    icon: str = ''
    connected: bool = False
    paired: bool = False
    trusted: bool = False
    rssi: int | None = None
    battery: int | None = None
    uuids: list[str] = field(default_factory=list)
    player: Player | None = None

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def supports_hfp(self) -> bool:
        """Handsfree Audio Gateway -- needed for calls."""
        return any(u.lower().startswith('0000111f') for u in self.uuids)

    @property
    def supports_pbap(self) -> bool:
        """Phonebook Access -- needed for contacts and call logs."""
        return any(u.lower().startswith('0000112f') for u in self.uuids)

    @property
    def supports_map(self) -> bool:
        """Message Access -- needed for SMS."""
        return any(u.lower().startswith('00001132') for u in self.uuids)


# --- Queries ---------------------------------------------------------------

async def managed_objects() -> dict[str, dict[str, Any]]:
    bus = system_bus()
    manager = DbusObjectManagerInterfaceAsync.new_proxy(SERVICE, '/', bus)
    return await manager.get_managed_objects()


async def inventory() -> list[Device]:
    """
    Every device BlueZ knows about, connected first.

    One GetManagedObjects call covers devices, batteries and players --
    walking the tree and introspecting each would be N+1 round trips.
    """
    objects = await managed_objects()

    # Index players by their parent device path first.
    raw_players: dict[str, tuple[str, dict]] = {}
    for path, interfaces in objects.items():
        mp = interfaces.get(IFACE_PLAYER)
        if mp is not None:
            raw_players[path.rsplit('/', 1)[0]] = (path, props(mp))

    devices: list[Device] = []
    for path, interfaces in objects.items():
        raw = interfaces.get(IFACE_DEVICE)
        if raw is None:
            continue
        p = props(raw)

        battery = None
        bat = interfaces.get(IFACE_BATTERY)
        if bat is not None:
            battery = props(bat).get('Percentage')

        player = None
        if path in raw_players:
            player_path, pp = raw_players[path]
            player = Player(
                path=player_path,
                device_path=path,
                device_name=p.get('Alias') or p.get('Name') or path,
                status=pp.get('Status', ''),
                position=pp.get('Position'),
                track=Track.from_props(pp.get('Track')),
            )

        devices.append(Device(
            path=path,
            address=p.get('Address', ''),
            name=p.get('Alias') or p.get('Name') or '(unnamed)',
            icon=p.get('Icon', ''),
            connected=bool(p.get('Connected', False)),
            paired=bool(p.get('Paired', False)),
            trusted=bool(p.get('Trusted', False)),
            rssi=p.get('RSSI'),
            battery=battery,
            uuids=list(p.get('UUIDs') or []),
            player=player,
        ))

    devices.sort(key=lambda d: (not d.connected, not d.paired,
                                d.name.lower()))
    return devices


async def players() -> list[Player]:
    """Just the devices that currently expose a media player."""
    return [d.player for d in await inventory() if d.player is not None]


def player_proxy(path: str) -> MediaPlayer1:
    return MediaPlayer1.new_proxy(SERVICE, path, system_bus())


def device_proxy(path: str) -> Device1:
    return Device1.new_proxy(SERVICE, path, system_bus())
