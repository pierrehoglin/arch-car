"""
systemd unit control over D-Bus.

Going through D-Bus rather than shelling out to systemctl matters for
authorisation: polkit sees the unit name in the action, so a rule can
grant exactly hostapd and iwd without granting root. Shelling out needs
sudoers rules that match on command-line strings, which broke twice
during development because argument order counts.

Grant access with /etc/polkit-1/rules.d/50-carunit.rules -- see
carlib/system/services.py for the rule.
"""

from sdbus import (
    DbusInterfaceCommonAsync,
    dbus_method_async,
    dbus_property_async,
)

from carlib.core.errors import NotAvailableError
from carlib.dbus.connection import system_bus

SERVICE = 'org.freedesktop.systemd1'
ROOT = '/org/freedesktop/systemd1'

IFACE_MANAGER = 'org.freedesktop.systemd1.Manager'
IFACE_UNIT = 'org.freedesktop.systemd1.Unit'

# Job modes. 'replace' is what systemctl uses by default.
MODE_REPLACE = 'replace'
MODE_FAIL = 'fail'


class Manager(DbusInterfaceCommonAsync,
              interface_name=IFACE_MANAGER):

    @dbus_method_async(input_signature='ss', result_signature='o')
    async def start_unit(self, name: str, mode: str) -> str:
        raise NotImplementedError

    @dbus_method_async(input_signature='ss', result_signature='o')
    async def stop_unit(self, name: str, mode: str) -> str:
        raise NotImplementedError

    @dbus_method_async(input_signature='ss', result_signature='o')
    async def restart_unit(self, name: str, mode: str) -> str:
        raise NotImplementedError

    @dbus_method_async(input_signature='ss', result_signature='o')
    async def reload_or_restart_unit(self, name: str, mode: str) -> str:
        raise NotImplementedError

    @dbus_method_async(input_signature='s', result_signature='o')
    async def load_unit(self, name: str) -> str:
        """
        Like GetUnit but loads the unit if systemd has not already.

        GetUnit raises for a stopped unit that nothing has referenced,
        which is exactly the case you hit when querying something that
        has never run this boot.
        """
        raise NotImplementedError

    @dbus_method_async(input_signature='asbb',
                       result_signature='ba(sss)')
    async def enable_unit_files(self, files: list[str], runtime: bool,
                                force: bool) -> tuple[bool, list]:
        raise NotImplementedError

    @dbus_method_async(input_signature='asb', result_signature='a(sss)')
    async def disable_unit_files(self, files: list[str],
                                 runtime: bool) -> list:
        raise NotImplementedError


class Unit(DbusInterfaceCommonAsync,
           interface_name=IFACE_UNIT):

    @dbus_property_async(property_signature='s')
    def id(self) -> str:
        raise NotImplementedError

    @dbus_property_async(property_signature='s')
    def description(self) -> str:
        raise NotImplementedError

    @dbus_property_async(property_signature='s')
    def load_state(self) -> str:
        raise NotImplementedError

    @dbus_property_async(property_signature='s')
    def active_state(self) -> str:
        raise NotImplementedError

    @dbus_property_async(property_signature='s')
    def sub_state(self) -> str:
        raise NotImplementedError

    @dbus_property_async(property_signature='s')
    def unit_file_state(self) -> str:
        raise NotImplementedError


def manager() -> Manager:
    return Manager.new_proxy(SERVICE, ROOT, system_bus())


def unit_proxy(path: str) -> Unit:
    return Unit.new_proxy(SERVICE, path, system_bus())


async def unit_path(name: str) -> str:
    """Object path for a unit, loading it if necessary."""
    try:
        return await manager().load_unit(name)
    except Exception as exc:
        raise NotAvailableError(
            f'cannot load unit {name}: {exc}',
            hint='is the unit installed?') from exc
