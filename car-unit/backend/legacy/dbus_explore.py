#!/usr/bin/env python3
"""
Basic D-Bus exploration with python-sdbus.

Install:
    sudo pacman -S python-sdbus
    # or: pip install --break-system-packages sdbus

Run:
    ./dbus_explore.py list-system
    ./dbus_explore.py list-session
    ./dbus_explore.py introspect org.freedesktop.systemd1 /org/freedesktop/systemd1
    ./dbus_explore.py unit-state hostapd.service
    ./dbus_explore.py hostname
"""

import sys
import asyncio

from sdbus import (
    sd_bus_open_system,
    sd_bus_open_user,
    set_default_bus,
    DbusInterfaceCommonAsync,
    dbus_method_async,
    dbus_property_async,
)


# --- Interface definitions -------------------------------------------------
# You describe the remote interface as a Python class. Method and property
# names are converted from snake_case to CamelCase automatically unless you
# override with the name= argument.

class DbusPeer(DbusInterfaceCommonAsync,
               interface_name='org.freedesktop.DBus'):

    @dbus_method_async(result_signature='as')
    async def list_names(self) -> list[str]:
        raise NotImplementedError


class SystemdManager(DbusInterfaceCommonAsync,
                     interface_name='org.freedesktop.systemd1.Manager'):

    @dbus_method_async(input_signature='s', result_signature='o')
    async def get_unit(self, name: str) -> str:
        raise NotImplementedError

    @dbus_method_async(input_signature='ss', result_signature='o')
    async def start_unit(self, name: str, mode: str) -> str:
        raise NotImplementedError

    @dbus_method_async(input_signature='ss', result_signature='o')
    async def stop_unit(self, name: str, mode: str) -> str:
        raise NotImplementedError


class SystemdUnit(DbusInterfaceCommonAsync,
                  interface_name='org.freedesktop.systemd1.Unit'):

    @dbus_property_async(property_signature='s')
    def active_state(self) -> str:
        raise NotImplementedError

    @dbus_property_async(property_signature='s')
    def sub_state(self) -> str:
        raise NotImplementedError

    @dbus_property_async(property_signature='s')
    def description(self) -> str:
        raise NotImplementedError


class Hostname1(DbusInterfaceCommonAsync,
                interface_name='org.freedesktop.hostname1'):

    @dbus_property_async(property_signature='s')
    def hostname(self) -> str:
        raise NotImplementedError

    @dbus_property_async(property_signature='s')
    def operating_system_pretty_name(self) -> str:
        raise NotImplementedError

    @dbus_property_async(property_signature='s')
    def kernel_release(self) -> str:
        raise NotImplementedError


# --- Commands --------------------------------------------------------------

async def list_names(system: bool) -> None:
    bus = sd_bus_open_system() if system else sd_bus_open_user()
    set_default_bus(bus)

    peer = DbusPeer.new_proxy(
        'org.freedesktop.DBus', '/org/freedesktop/DBus', bus)

    names = await peer.list_names()
    # Unique names start with ':' and are just connection ids, so hide them.
    for name in sorted(n for n in names if not n.startswith(':')):
        print(name)


async def introspect(service: str, path: str, system: bool = True) -> None:
    bus = sd_bus_open_system() if system else sd_bus_open_user()
    set_default_bus(bus)

    # Every object implements org.freedesktop.DBus.Introspectable.
    proxy = DbusInterfaceCommonAsync.new_proxy(service, path, bus)
    print(await proxy.dbus_introspect())


async def unit_state(unit_name: str) -> None:
    bus = sd_bus_open_system()
    set_default_bus(bus)

    manager = SystemdManager.new_proxy(
        'org.freedesktop.systemd1', '/org/freedesktop/systemd1', bus)

    unit_path = await manager.get_unit(unit_name)
    unit = SystemdUnit.new_proxy('org.freedesktop.systemd1', unit_path, bus)

    print(f'unit:        {unit_name}')
    print(f'path:        {unit_path}')
    print(f'description: {await unit.description}')
    print(f'active:      {await unit.active_state}')
    print(f'sub:         {await unit.sub_state}')


async def show_hostname() -> None:
    bus = sd_bus_open_system()
    set_default_bus(bus)

    h = Hostname1.new_proxy(
        'org.freedesktop.hostname1', '/org/freedesktop/hostname1', bus)

    print(f'hostname: {await h.hostname}')
    print(f'os:       {await h.operating_system_pretty_name}')
    print(f'kernel:   {await h.kernel_release}')


# --- Entry point -----------------------------------------------------------

def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__.strip())
        return 1

    cmd, args = sys.argv[1], sys.argv[2:]

    try:
        if cmd == 'list-system':
            asyncio.run(list_names(system=True))
        elif cmd == 'list-session':
            asyncio.run(list_names(system=False))
        elif cmd == 'introspect':
            if len(args) != 2:
                print('usage: introspect SERVICE PATH')
                return 1
            asyncio.run(introspect(args[0], args[1]))
        elif cmd == 'unit-state':
            if len(args) != 1:
                print('usage: unit-state UNIT.service')
                return 1
            asyncio.run(unit_state(args[0]))
        elif cmd == 'hostname':
            asyncio.run(show_hostname())
        else:
            print(f'unknown command: {cmd}')
            print(__doc__.strip())
            return 1
    except Exception as exc:
        print(f'error: {exc}', file=sys.stderr)
        return 1

    return 0


if __name__ == '__main__':
    sys.exit(main())
