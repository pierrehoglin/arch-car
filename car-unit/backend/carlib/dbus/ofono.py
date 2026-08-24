"""
oFono: modems, calls, handsfree, call volume.

oFono handles HFP call control; BlueZ does not. The two must not both
claim the HFP profile -- see HFP_SERVICE_ORDERING.md.
"""

from dataclasses import dataclass, field, asdict

from sdbus import (
    DbusInterfaceCommonAsync,
    dbus_method_async,
    dbus_signal_async,
)

from carlib.dbus.connection import system_bus
from carlib.core.errors import NotAvailableError
from carlib.dbus.variants import props

SERVICE = 'org.ofono'

IFACE_VOICECALL_MANAGER = 'org.ofono.VoiceCallManager'
IFACE_NETWORK_REGISTRATION = 'org.ofono.NetworkRegistration'
IFACE_HANDSFREE = 'org.ofono.Handsfree'
IFACE_CALL_VOLUME = 'org.ofono.CallVolume'


# --- Interfaces ------------------------------------------------------------

class Manager(DbusInterfaceCommonAsync,
              interface_name='org.ofono.Manager'):

    @dbus_method_async(result_signature='a(oa{sv})')
    async def get_modems(self) -> list[tuple[str, dict]]:
        raise NotImplementedError

    @dbus_signal_async('oa{sv}')
    def modem_added(self) -> tuple[str, dict]:
        raise NotImplementedError

    @dbus_signal_async('o')
    def modem_removed(self) -> str:
        raise NotImplementedError


class Modem(DbusInterfaceCommonAsync,
            interface_name='org.ofono.Modem'):

    @dbus_method_async(result_signature='a{sv}')
    async def get_properties(self) -> dict:
        raise NotImplementedError

    @dbus_method_async(input_signature='sv')
    async def set_property(self, name: str,
                           value: tuple[str, object]) -> None:
        raise NotImplementedError


class VoiceCallManager(DbusInterfaceCommonAsync,
                       interface_name=IFACE_VOICECALL_MANAGER):

    @dbus_method_async(input_signature='ss', result_signature='o')
    async def dial(self, number: str, hide_callerid: str) -> str:
        raise NotImplementedError

    @dbus_method_async(result_signature='a(oa{sv})')
    async def get_calls(self) -> list[tuple[str, dict]]:
        raise NotImplementedError

    @dbus_method_async()
    async def hangup_all(self) -> None:
        raise NotImplementedError

    @dbus_method_async()
    async def answer(self) -> None:
        raise NotImplementedError

    @dbus_method_async()
    async def hold_and_answer(self) -> None:
        raise NotImplementedError

    @dbus_method_async()
    async def swap_calls(self) -> None:
        raise NotImplementedError

    @dbus_signal_async('oa{sv}')
    def call_added(self) -> tuple[str, dict]:
        raise NotImplementedError

    @dbus_signal_async('o')
    def call_removed(self) -> str:
        raise NotImplementedError


class VoiceCall(DbusInterfaceCommonAsync,
                interface_name='org.ofono.VoiceCall'):

    @dbus_method_async(result_signature='a{sv}')
    async def get_properties(self) -> dict:
        raise NotImplementedError

    @dbus_method_async()
    async def hangup(self) -> None:
        raise NotImplementedError

    @dbus_method_async()
    async def answer(self) -> None:
        raise NotImplementedError


class NetworkRegistration(DbusInterfaceCommonAsync,
                          interface_name=IFACE_NETWORK_REGISTRATION):

    @dbus_method_async(result_signature='a{sv}')
    async def get_properties(self) -> dict:
        raise NotImplementedError


class Handsfree(DbusInterfaceCommonAsync,
                interface_name=IFACE_HANDSFREE):

    @dbus_method_async(result_signature='a{sv}')
    async def get_properties(self) -> dict:
        raise NotImplementedError

    @dbus_method_async(input_signature='sv')
    async def set_property(self, name: str,
                           value: tuple[str, object]) -> None:
        raise NotImplementedError

    @dbus_method_async(input_signature='s')
    async def send_tones(self, tones: str) -> None:
        raise NotImplementedError


class CallVolume(DbusInterfaceCommonAsync,
                 interface_name=IFACE_CALL_VOLUME):

    @dbus_method_async(result_signature='a{sv}')
    async def get_properties(self) -> dict:
        raise NotImplementedError

    @dbus_method_async(input_signature='sv')
    async def set_property(self, name: str,
                           value: tuple[str, object]) -> None:
        raise NotImplementedError


# --- Data ------------------------------------------------------------------

@dataclass
class ModemInfo:
    path: str
    name: str
    serial: str = ''
    type: str = ''
    powered: bool = False
    online: bool = False
    interfaces: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def ready(self) -> bool:
        """Can we actually place a call on this modem right now?"""
        return IFACE_VOICECALL_MANAGER in self.interfaces


# --- Queries ---------------------------------------------------------------

def manager() -> Manager:
    return Manager.new_proxy(SERVICE, '/', system_bus())


async def modems() -> list[ModemInfo]:
    try:
        raw = await manager().get_modems()
    except Exception as exc:
        raise NotAvailableError(
            f'cannot reach oFono: {exc}',
            hint='is ofono.service running, and does your user have '
                 'D-Bus access to org.ofono?') from exc

    result = []
    for path, raw_props in raw:
        p = props(raw_props)
        result.append(ModemInfo(
            path=path,
            name=p.get('Name', '?'),
            serial=p.get('Serial', ''),
            type=p.get('Type', ''),
            powered=bool(p.get('Powered', False)),
            online=bool(p.get('Online', False)),
            interfaces=list(p.get('Interfaces') or []),
        ))
    return result


def modem_proxy(path: str) -> Modem:
    return Modem.new_proxy(SERVICE, path, system_bus())


def calls_proxy(path: str) -> VoiceCallManager:
    return VoiceCallManager.new_proxy(SERVICE, path, system_bus())


def call_proxy(path: str) -> VoiceCall:
    return VoiceCall.new_proxy(SERVICE, path, system_bus())


def handsfree_proxy(path: str) -> Handsfree:
    return Handsfree.new_proxy(SERVICE, path, system_bus())


def volume_proxy(path: str) -> CallVolume:
    return CallVolume.new_proxy(SERVICE, path, system_bus())


def network_proxy(path: str) -> NetworkRegistration:
    return NetworkRegistration.new_proxy(SERVICE, path, system_bus())
