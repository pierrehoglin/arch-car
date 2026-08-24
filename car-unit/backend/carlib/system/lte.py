"""
LTE connection status.

Reads ModemManager directly rather than NetworkManager, because the
modem knows things NM does not: signal quality, access technology,
operator, and whether the bearer is actually carrying bytes.

That last point matters. A modem can be registered, attached and
holding an IP address while the carrier routes nothing — the bearer
statistics are the only way to tell from this side. `connected` here
means a bearer exists; `carrying` means data has moved.
"""

from dataclasses import dataclass, asdict

from sdbus import (
    DbusInterfaceCommonAsync,
    dbus_property_async,
)

from carlib.core.errors import NotAvailableError
from carlib.core.match import select_optional
from carlib.dbus import modemmanager as mm
from carlib.dbus.connection import system_bus
from carlib.dbus.variants import props

IFACE_BEARER = 'org.freedesktop.ModemManager1.Bearer'

# MMModem3gppRegistrationState
REGISTRATION = {
    0: 'idle',
    1: 'home',
    2: 'searching',
    3: 'denied',
    4: 'unknown',
    5: 'roaming',
}


class Bearer(DbusInterfaceCommonAsync,
             interface_name=IFACE_BEARER):

    @dbus_property_async(property_signature='b')
    def connected(self) -> bool:
        raise NotImplementedError

    @dbus_property_async(property_signature='s')
    def interface(self) -> str:
        raise NotImplementedError

    @dbus_property_async(property_signature='a{sv}')
    def ip4_config(self) -> dict:
        raise NotImplementedError

    @dbus_property_async(property_signature='a{sv}')
    def properties(self) -> dict:
        raise NotImplementedError

    @dbus_property_async(property_signature='a{sv}')
    def stats(self) -> dict:
        raise NotImplementedError


@dataclass
class LteState:
    present: bool = False
    state: str = 'unknown'
    registration: str = ''
    operator: str = ''
    access_technology: str = ''
    signal: int = 0

    connected: bool = False
    interface: str = ''
    ip_address: str = ''
    apn: str = ''

    bytes_rx: int = 0
    bytes_tx: int = 0
    duration: int = 0

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def bars(self) -> str:
        """Signal as a four-step bar."""
        filled = min(4, max(0, round(self.signal / 25)))
        return '\u2588' * filled + '\u2591' * (4 - filled)

    @property
    def carrying(self) -> bool:
        """
        Whether data has actually moved.

        A bearer can be up with the carrier discarding everything, which
        shows as high tx and near-zero rx.
        """
        return self.bytes_rx > 4096

    @property
    def summary(self) -> str:
        if not self.present:
            return 'no modem'
        if not self.connected:
            return f'{self.state}'
        return f'{self.operator} {self.access_technology}'.strip()


async def _bearer_state(modem_path: str) -> dict:
    """
    Find the data bearer and read it.

    Bearers are NOT in GetManagedObjects -- ModemManager's ObjectManager
    exposes modems and SIMs only. The paths come from the modem's own
    Bearers property, and each is then proxied directly.

    A SIM7600 exposes two: an initial EPS attach bearer created at
    registration, and the actual data bearer. Both report connected,
    but only the data one has a network interface, so that is the
    discriminator.
    """
    bus = system_bus()

    modem = mm.Modem.new_proxy(mm.SERVICE, modem_path, bus)
    try:
        paths = await modem.bearers
    except Exception:
        return {}

    fallback = {}
    for path in paths:
        try:
            bearer = Bearer.new_proxy(mm.SERVICE, path, bus)
            if not await bearer.connected:
                continue

            iface = await bearer.interface or ''
            ip4 = props(await bearer.ip4_config)
            settings = props(await bearer.properties)
            stats = props(await bearer.stats)
        except Exception:
            continue

        candidate = {
            'connected': True,
            'interface': iface,
            'ip_address': ip4.get('address', ''),
            'apn': settings.get('apn', ''),
            'bytes_rx': int(stats.get('rx-bytes', 0) or 0),
            'bytes_tx': int(stats.get('tx-bytes', 0) or 0),
            'duration': int(stats.get('duration', 0) or 0),
        }

        # The bearer with a network interface is the data one; the
        # attach bearer has none.
        if iface:
            return candidate
        fallback = fallback or candidate

    return fallback


async def status(match: str | None = None) -> LteState:
    """Current LTE state, or present=False when there is no modem."""
    try:
        modems = await mm.modems()
    except NotAvailableError:
        return LteState(present=False, state='modemmanager unavailable')

    if not modems:
        return LteState(present=False, state='no modem')

    modem = select_optional(
        modems, match,
        what='modem',
        keys=lambda m: (m.path, m.model, m.manufacturer),
        label=lambda m: m.model or m.path,
    )

    state = LteState(
        present=True,
        state=modem.state,
        operator=modem.operator,
        access_technology=modem.access_technology,
        signal=modem.signal_quality,
    )

    try:
        gpp = props(await mm.gpp_proxy(modem.path).get_properties())
        state.registration = REGISTRATION.get(
            gpp.get('RegistrationState', 4), 'unknown')
    except Exception:
        pass

    try:
        bearer = await _bearer_state(modem.path)
        if bearer:
            state.connected = True
            state.interface = bearer['interface']
            state.ip_address = bearer['ip_address']
            state.apn = bearer['apn']
            state.bytes_rx = bearer['bytes_rx']
            state.bytes_tx = bearer['bytes_tx']
            state.duration = bearer['duration']
    except Exception:
        pass

    return state


def format_bytes(count: int) -> str:
    for unit in ('B', 'KB', 'MB', 'GB'):
        if count < 1024 or unit == 'GB':
            return f'{count:.0f} {unit}' if unit == 'B' \
                else f'{count:.1f} {unit}'
        count /= 1024.0
    return f'{count:.1f} GB'


def format_duration(seconds: int) -> str:
    if seconds < 60:
        return f'{seconds}s'
    if seconds < 3600:
        return f'{seconds // 60}m {seconds % 60}s'
    return f'{seconds // 3600}h {(seconds % 3600) // 60}m'
