"""
ModemManager interfaces: modem, location, 3GPP registration, signal.

Signatures taken from `busctl --system introspect` against a
SIM7600E-H on the simtech plugin. ModemManager is stable across
releases here, but if a method errors with "doesn't exist", introspect
and compare.

ModemManager needs polkit authorisation. To run unprivileged:

    /etc/polkit-1/rules.d/50-modemmanager.rules
    polkit.addRule(function(action, subject) {
        if (action.id.indexOf("org.freedesktop.ModemManager1.") === 0 &&
            subject.user == "alarm") {
            return polkit.Result.YES;
        }
    });
"""

from dataclasses import dataclass, field, asdict

from sdbus import (
    DbusInterfaceCommonAsync,
    DbusObjectManagerInterfaceAsync,
    dbus_method_async,
    dbus_property_async,
    dbus_signal_async,
)

from carlib.dbus.connection import system_bus
from carlib.core.errors import NotAvailableError
from carlib.dbus.variants import props

SERVICE = 'org.freedesktop.ModemManager1'
ROOT = '/org/freedesktop/ModemManager1'

IFACE_MODEM = 'org.freedesktop.ModemManager1.Modem'
IFACE_LOCATION = 'org.freedesktop.ModemManager1.Modem.Location'
IFACE_3GPP = 'org.freedesktop.ModemManager1.Modem.Modem3gpp'
IFACE_SIGNAL = 'org.freedesktop.ModemManager1.Modem.Signal'


# --- MMModemLocationSource bitmask -----------------------------------------

SOURCE_NONE = 0
SOURCE_3GPP_LAC_CI = 1 << 0      # 1   coarse, from the cell tower
SOURCE_GPS_RAW = 1 << 1          # 2   parsed lat/lon from ModemManager
SOURCE_GPS_NMEA = 1 << 2         # 4   raw NMEA sentences
SOURCE_CDMA_BS = 1 << 3          # 8
SOURCE_GPS_UNMANAGED = 1 << 4    # 16  hands the TTY to another process
SOURCE_AGPS_MSA = 1 << 5         # 32  assisted, mobile-station-assisted
SOURCE_AGPS_MSB = 1 << 6         # 64  assisted, mobile-station-based

SOURCE_NAMES = {
    SOURCE_3GPP_LAC_CI: '3gpp-lac-ci',
    SOURCE_GPS_RAW: 'gps-raw',
    SOURCE_GPS_NMEA: 'gps-nmea',
    SOURCE_CDMA_BS: 'cdma-bs',
    SOURCE_GPS_UNMANAGED: 'gps-unmanaged',
    SOURCE_AGPS_MSA: 'agps-msa',
    SOURCE_AGPS_MSB: 'agps-msb',
}


def decode_sources(mask: int) -> list[str]:
    """Turn a location source bitmask into readable names."""
    return [name for bit, name in SOURCE_NAMES.items() if mask & bit]


# --- MMModemState ----------------------------------------------------------

MODEM_STATES = {
    -1: 'failed',
    0: 'unknown',
    1: 'initializing',
    2: 'locked',
    3: 'disabled',
    4: 'disabling',
    5: 'enabling',
    6: 'enabled',
    7: 'searching',
    8: 'registered',
    9: 'disconnecting',
    10: 'connecting',
    11: 'connected',
}

ACCESS_TECH = {
    0: 'unknown', 1: 'pots', 2: 'gsm', 4: 'gsm-compact',
    8: 'gprs', 16: 'edge', 32: 'umts', 64: 'hsdpa',
    128: 'hsupa', 256: 'hspa', 512: 'hspa-plus', 1024: 'evdo0',
    2048: 'evdoa', 4096: 'evdob', 8192: 'lte', 16384: 'lte',
    32768: '5gnr',
}


# --- Interfaces ------------------------------------------------------------

class Modem(DbusInterfaceCommonAsync,
            interface_name=IFACE_MODEM):

    @dbus_method_async(input_signature='b')
    async def enable(self, enable: bool) -> None:
        raise NotImplementedError

    @dbus_method_async(input_signature='su', result_signature='s')
    async def command(self, cmd: str, timeout: int) -> str:
        raise NotImplementedError

    @dbus_property_async(property_signature='s')
    def model(self) -> str:
        raise NotImplementedError

    @dbus_property_async(property_signature='s')
    def manufacturer(self) -> str:
        raise NotImplementedError

    @dbus_property_async(property_signature='i')
    def state(self) -> int:
        raise NotImplementedError

    @dbus_property_async(property_signature='(ub)')
    def signal_quality(self) -> tuple[int, bool]:
        raise NotImplementedError

    @dbus_property_async(property_signature='u')
    def access_technologies(self) -> int:
        raise NotImplementedError

    @dbus_property_async(property_signature='ao')
    def bearers(self) -> list[str]:
        """
        Object paths of this modem's bearers.

        Bearers are not exposed through GetManagedObjects -- this
        property is the only way to enumerate them.
        """
        raise NotImplementedError

    @dbus_method_async(result_signature='ao')
    async def list_bearers(self) -> list[str]:
        raise NotImplementedError

    @dbus_signal_async('iiu')
    def state_changed(self) -> tuple[int, int, int]:
        raise NotImplementedError


class Location(DbusInterfaceCommonAsync,
               interface_name=IFACE_LOCATION):

    @dbus_method_async(result_signature='a{uv}')
    async def get_location(self) -> dict[int, tuple[str, object]]:
        raise NotImplementedError

    @dbus_method_async(input_signature='ub')
    async def setup(self, sources: int, signal_location: bool) -> None:
        raise NotImplementedError

    @dbus_method_async(input_signature='u')
    async def set_gps_refresh_rate(self, rate: int) -> None:
        raise NotImplementedError

    @dbus_method_async(input_signature='s')
    async def set_supl_server(self, server: str) -> None:
        raise NotImplementedError

    @dbus_property_async(property_signature='u')
    def capabilities(self) -> int:
        raise NotImplementedError

    @dbus_property_async(property_signature='u')
    def enabled(self) -> int:
        raise NotImplementedError

    @dbus_property_async(property_signature='u')
    def gps_refresh_rate(self) -> int:
        raise NotImplementedError

    @dbus_property_async(property_signature='b')
    def signals_location(self) -> bool:
        raise NotImplementedError

    @dbus_property_async(property_signature='s')
    def supl_server(self) -> str:
        raise NotImplementedError

    @dbus_property_async(property_signature='a{uv}')
    def location(self) -> dict[int, tuple[str, object]]:
        raise NotImplementedError


class Modem3gpp(DbusInterfaceCommonAsync,
                interface_name=IFACE_3GPP):

    @dbus_property_async(property_signature='s')
    def operator_name(self) -> str:
        raise NotImplementedError

    @dbus_property_async(property_signature='s')
    def operator_code(self) -> str:
        raise NotImplementedError

    @dbus_property_async(property_signature='u')
    def registration_state(self) -> int:
        raise NotImplementedError


# --- Data ------------------------------------------------------------------

@dataclass
class ModemInfo:
    path: str
    model: str = ''
    manufacturer: str = ''
    state: str = 'unknown'
    signal_quality: int = 0
    access_technology: str = ''
    operator: str = ''
    location_capabilities: list[str] = field(default_factory=list)
    location_enabled: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def has_gps(self) -> bool:
        return 'gps-nmea' in self.location_capabilities \
            or 'gps-raw' in self.location_capabilities

    @property
    def gps_active(self) -> bool:
        return 'gps-nmea' in self.location_enabled \
            or 'gps-raw' in self.location_enabled


# --- Queries ---------------------------------------------------------------

async def managed_objects() -> dict:
    bus = system_bus()
    manager = DbusObjectManagerInterfaceAsync.new_proxy(SERVICE, ROOT, bus)
    try:
        return await manager.get_managed_objects()
    except Exception as exc:
        raise NotAvailableError(
            f'cannot reach ModemManager: {exc}',
            hint='is ModemManager.service running?') from exc


async def modems() -> list[ModemInfo]:
    """Every modem ModemManager knows about."""
    objects = await managed_objects()

    result = []
    for path, interfaces in objects.items():
        raw = interfaces.get(IFACE_MODEM)
        if raw is None:
            continue
        p = props(raw)

        quality = p.get('SignalQuality') or (0, False)
        if isinstance(quality, tuple):
            quality = quality[0]

        loc = props(interfaces.get(IFACE_LOCATION) or {})
        gpp = props(interfaces.get(IFACE_3GPP) or {})

        result.append(ModemInfo(
            path=path,
            model=p.get('Model', ''),
            manufacturer=p.get('Manufacturer', ''),
            state=MODEM_STATES.get(p.get('State', 0), 'unknown'),
            signal_quality=quality,
            access_technology=ACCESS_TECH.get(
                p.get('AccessTechnologies', 0), 'unknown'),
            operator=gpp.get('OperatorName', ''),
            location_capabilities=decode_sources(loc.get('Capabilities', 0)),
            location_enabled=decode_sources(loc.get('Enabled', 0)),
        ))

    return result


def modem_proxy(path: str) -> Modem:
    return Modem.new_proxy(SERVICE, path, system_bus())


def location_proxy(path: str) -> Location:
    return Location.new_proxy(SERVICE, path, system_bus())


def gpp_proxy(path: str) -> Modem3gpp:
    return Modem3gpp.new_proxy(SERVICE, path, system_bus())
