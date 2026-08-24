"""
CAN bus via socketcan.

Unlike the rest of carlib this does not touch D-Bus. socketcan presents
the bus as a network interface, so the kernel does the transport and
python-can does the framing.

    sudo pacman -S can-utils
    uv add python-can

Bring an interface up before use. Most cars run 500 kbit/s on the
powertrain bus and 125 kbit/s on the comfort bus:

    sudo ip link set can0 type can bitrate 500000
    sudo ip link set can0 up

For testing without hardware, socketcan has a virtual interface:

    sudo modprobe vcan
    sudo ip link set up vcan0        (after `ip link add dev vcan0 type vcan`)

A word of caution: writing to a vehicle's CAN bus can affect how it
behaves. Read first, and know what a frame does before you send it.
"""

import asyncio
from dataclasses import dataclass, field, asdict
from typing import AsyncIterator, Callable

from carlib.core.errors import NotAvailableError

DEFAULT_BITRATE = 500_000


@dataclass
class Frame:
    """One CAN frame."""

    arbitration_id: int
    data: bytes
    timestamp: float = 0.0
    is_extended: bool = False
    is_remote: bool = False
    is_error: bool = False
    channel: str = ''

    def to_dict(self) -> dict:
        d = asdict(self)
        d['data'] = self.data.hex()
        d['arbitration_id_hex'] = self.hex_id
        return d

    @property
    def hex_id(self) -> str:
        width = 8 if self.is_extended else 3
        return f'{self.arbitration_id:0{width}X}'

    @property
    def dlc(self) -> int:
        return len(self.data)

    def __str__(self) -> str:
        return f'{self.hex_id}  [{self.dlc}]  {self.data.hex(" ").upper()}'

    @classmethod
    def from_message(cls, msg, channel: str = '') -> 'Frame':
        """Adapt a python-can Message, keeping python-can out of the API."""
        return cls(
            arbitration_id=msg.arbitration_id,
            data=bytes(msg.data or b''),
            timestamp=getattr(msg, 'timestamp', 0.0),
            is_extended=bool(getattr(msg, 'is_extended_id', False)),
            is_remote=bool(getattr(msg, 'is_remote_frame', False)),
            is_error=bool(getattr(msg, 'is_error_frame', False)),
            channel=channel or str(getattr(msg, 'channel', '') or ''),
        )


@dataclass
class Signal:
    """
    One decoded value within a frame.

    CAN packs several signals into eight bytes, so a decoder turns a
    Frame into a handful of these.
    """

    name: str
    value: float | int | str
    unit: str = ''
    raw: int = 0

    def to_dict(self) -> dict:
        return asdict(self)

    def __str__(self) -> str:
        unit = f' {self.unit}' if self.unit else ''
        return f'{self.name}: {self.value}{unit}'


@dataclass
class Stats:
    """Running counts, for a status display."""

    frames: int = 0
    errors: int = 0
    unique_ids: set = field(default_factory=set)
    first_timestamp: float = 0.0
    last_timestamp: float = 0.0

    def record(self, frame: Frame) -> None:
        self.frames += 1
        if frame.is_error:
            self.errors += 1
        self.unique_ids.add(frame.arbitration_id)
        if not self.first_timestamp:
            self.first_timestamp = frame.timestamp
        self.last_timestamp = frame.timestamp

    @property
    def duration(self) -> float:
        return max(0.0, self.last_timestamp - self.first_timestamp)

    @property
    def rate(self) -> float:
        """Frames per second."""
        return self.frames / self.duration if self.duration else 0.0

    def to_dict(self) -> dict:
        return {
            'frames': self.frames,
            'errors': self.errors,
            'unique_ids': len(self.unique_ids),
            'duration': round(self.duration, 2),
            'rate': round(self.rate, 1),
        }


def _require_can():
    """
    Import python-can lazily.

    Keeps `import carlib.vehicle.can` cheap and gives a useful error
    instead of a bare ImportError when the dependency is missing.
    """
    try:
        import can
    except ImportError as exc:
        raise NotAvailableError(
            'python-can is not installed',
            hint='uv add python-can') from exc
    return can


def interfaces() -> list[str]:
    """Every CAN interface the kernel knows about, up or down."""
    import pathlib
    found = []
    for path in sorted(pathlib.Path('/sys/class/net').glob('*')):
        try:
            uevent = (path / 'uevent').read_text()
        except OSError:
            continue
        if 'DEVTYPE=can' in uevent or path.name.startswith(('can', 'vcan')):
            found.append(path.name)
    return found


def is_up(channel: str) -> bool:
    import pathlib
    try:
        state = pathlib.Path(f'/sys/class/net/{channel}/operstate').read_text()
    except OSError:
        return False
    return state.strip() in ('up', 'unknown')


def open_bus(channel: str = 'can0'):
    """
    Open a socketcan bus.

    The caller owns the returned object and must call shutdown(); the
    listen helpers below handle that for you.
    """
    can = _require_can()

    if channel not in interfaces():
        raise NotAvailableError(
            f'no CAN interface named {channel!r}',
            hint=f'available: {", ".join(interfaces()) or "none"}. '
                 f'Create one with: sudo ip link set {channel} type can '
                 f'bitrate {DEFAULT_BITRATE}')

    if not is_up(channel):
        raise NotAvailableError(
            f'{channel} is down',
            hint=f'sudo ip link set {channel} up')

    try:
        return can.interface.Bus(channel=channel, interface='socketcan')
    except Exception as exc:
        raise NotAvailableError(
            f'cannot open {channel}: {exc}') from exc


async def listen(channel: str = 'can0',
                 ids: set[int] | None = None,
                 limit: int | None = None,
                 timeout: float = 1.0) -> AsyncIterator[Frame]:
    """
    Yield frames as they arrive.

        async for frame in can.listen('can0', ids={0x7E8}):
            print(frame)

    ids filters by arbitration ID; None passes everything. Reading is
    blocking, so it runs in a thread to keep the event loop free.
    """
    bus = open_bus(channel)
    seen = 0
    loop = asyncio.get_running_loop()

    try:
        while limit is None or seen < limit:
            msg = await loop.run_in_executor(None, bus.recv, timeout)
            if msg is None:
                continue
            if ids is not None and msg.arbitration_id not in ids:
                continue
            seen += 1
            yield Frame.from_message(msg, channel)
    finally:
        await loop.run_in_executor(None, bus.shutdown)


async def sniff(channel: str = 'can0',
                duration: float = 10.0) -> tuple[Stats, dict[int, Frame]]:
    """
    Watch the bus for a while and report what is on it.

    Returns overall statistics plus the most recent frame per ID --
    the starting point for working out what an unknown bus carries.
    """
    stats = Stats()
    latest: dict[int, Frame] = {}

    loop = asyncio.get_running_loop()
    deadline = loop.time() + duration

    async for frame in listen(channel, timeout=0.5):
        stats.record(frame)
        latest[frame.arbitration_id] = frame
        if loop.time() >= deadline:
            break

    return stats, latest


async def send(channel: str,
               arbitration_id: int,
               data: bytes,
               extended: bool = False) -> None:
    """
    Transmit one frame.

    Be careful on a live vehicle bus: an unknown ID can trigger real
    behaviour. Test on vcan first.
    """
    can = _require_can()
    bus = open_bus(channel)
    loop = asyncio.get_running_loop()

    msg = can.Message(
        arbitration_id=arbitration_id,
        data=data,
        is_extended_id=extended,
    )
    try:
        await loop.run_in_executor(None, bus.send, msg)
    finally:
        await loop.run_in_executor(None, bus.shutdown)


# --- Decoding --------------------------------------------------------------

Decoder = Callable[[Frame], list[Signal]]

_decoders: dict[int, Decoder] = {}


def register(arbitration_id: int) -> Callable[[Decoder], Decoder]:
    """
    Register a decoder for one arbitration ID.

        @can.register(0x1A0)
        def speed(frame):
            raw = int.from_bytes(frame.data[0:2], 'big')
            return [Signal('speed', raw * 0.01, 'km/h', raw)]

    Vehicle-specific by nature -- IDs and packing differ per make, and
    are usually reverse-engineered from a sniff.
    """
    def wrap(fn: Decoder) -> Decoder:
        _decoders[arbitration_id] = fn
        return fn
    return wrap


def decode(frame: Frame) -> list[Signal]:
    """Decode a frame, or return an empty list if no decoder is registered."""
    decoder = _decoders.get(frame.arbitration_id)
    if decoder is None:
        return []
    try:
        return decoder(frame)
    except Exception:
        # A bad decoder should not kill the stream.
        return []


def known_ids() -> list[int]:
    return sorted(_decoders)
