"""
Bluetooth power control.

Two different things get called "turning Bluetooth off":

    radio off    Adapter1.Powered = false. Instant, keeps bluetoothd
                 running, pairings intact, reversible in milliseconds.
                 This is what a phone's Bluetooth toggle does.

    service off  systemctl stop bluetooth. Slower, tears down the
                 daemon, and anything holding a profile (oFono for HFP)
                 loses its registration.

Prefer the radio for a UI toggle. Use the service only when you
actually want the daemon gone -- and remember oFono is PartOf
bluetooth.service, so stopping it takes HFP with it.
"""

from dataclasses import dataclass, asdict

from sdbus import DbusObjectManagerInterfaceAsync

from carlib.core.errors import NotAvailableError, NotFoundError
from carlib.dbus import bluez
from carlib.dbus.connection import system_bus
from carlib.dbus.variants import props
from carlib.system import services


@dataclass
class AdapterState:
    path: str
    address: str = ''
    name: str = ''
    powered: bool = False
    discoverable: bool = False
    pairable: bool = False
    discovering: bool = False
    service_active: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


async def adapters() -> list[AdapterState]:
    """Every Bluetooth adapter BlueZ knows about."""
    bus = system_bus()
    manager = DbusObjectManagerInterfaceAsync.new_proxy(
        bluez.SERVICE, '/', bus)

    try:
        objects = await manager.get_managed_objects()
    except Exception as exc:
        raise NotAvailableError(
            f'cannot reach BlueZ: {exc}',
            hint='is bluetooth.service running?') from exc

    found = []
    for path, interfaces in objects.items():
        raw = interfaces.get(bluez.IFACE_ADAPTER)
        if raw is None:
            continue
        p = props(raw)
        found.append(AdapterState(
            path=path,
            address=p.get('Address', ''),
            name=p.get('Alias') or p.get('Name') or '',
            powered=bool(p.get('Powered', False)),
            discoverable=bool(p.get('Discoverable', False)),
            pairable=bool(p.get('Pairable', False)),
            discovering=bool(p.get('Discovering', False)),
        ))
    return found


async def default_adapter() -> AdapterState:
    found = await adapters()
    if not found:
        raise NotFoundError('adapter', 'hci0', [])
    return found[0]


async def status() -> AdapterState:
    """Adapter state plus whether the daemon is running."""
    try:
        svc = await services.status('bluetooth')
        service_active = svc.active
    except Exception:
        service_active = False

    if not service_active:
        return AdapterState(path='', service_active=False)

    adapter = await default_adapter()
    adapter.service_active = True
    return adapter


async def set_powered(on: bool) -> AdapterState:
    """
    Power the radio on or off without touching the daemon.

    Powering on requires bluetooth.service to be running -- there is no
    adapter object otherwise.
    """
    svc = await services.status('bluetooth')
    if not svc.active:
        if not on:
            return AdapterState(path='', service_active=False)
        await services.start('bluetooth')

    adapter = await default_adapter()
    proxy = bluez.Adapter1.new_proxy(
        bluez.SERVICE, adapter.path, system_bus())

    try:
        await proxy.powered.set_async(on)
    except Exception as exc:
        raise NotAvailableError(
            f'cannot set adapter power: {exc}',
            hint='BlueZ needs polkit permission, or add your user to '
                 'the lp group') from exc

    return await status()


async def toggle_power() -> AdapterState:
    current = await status()
    return await set_powered(not current.powered)


async def set_discoverable(on: bool, timeout: int | None = None
                           ) -> AdapterState:
    """
    Make the adapter visible to other devices.

    A timeout of 0 means indefinitely, which is usually what a car unit
    wants -- the default of 180 seconds means a passenger cannot pair
    unless you toggle it first.
    """
    adapter = await default_adapter()
    proxy = bluez.Adapter1.new_proxy(
        bluez.SERVICE, adapter.path, system_bus())

    if timeout is not None:
        await proxy.discoverable_timeout.set_async(timeout)
    await proxy.discoverable.set_async(on)
    if on:
        await proxy.pairable.set_async(True)

    return await status()


async def service_start() -> AdapterState:
    await services.start('bluetooth')
    return await status()


async def service_stop() -> AdapterState:
    await services.stop('bluetooth')
    return AdapterState(path='', service_active=False)
