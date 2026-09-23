"""
Bluetooth: the service, the adapter, and the devices on it.

Stateless -- each call reads what it needs from BlueZ and returns.
Anything that has to persist between calls (a pairing window, an agent
waiting for an answer) lives in carlib.bluetooth.pairing, which only
the daemon runs.

On and off means the service, not the radio. Stopping bluetooth.service
tears down the daemon, and oFono is PartOf it, so HFP goes too -- which
is what off should mean in a car. A radio toggle would leave both
running for nothing.
"""

from dataclasses import dataclass, asdict

from sdbus import DbusObjectManagerInterfaceAsync

from carlib.core.errors import NotAvailableError, NotFoundError
from carlib.dbus import bluez
from carlib.dbus.connection import system_bus
from carlib.dbus.variants import props
from carlib.system import services

SERVICE = 'bluetooth'


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
            hint='bt start') from exc

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


def _adapter(path: str) -> bluez.Adapter1:
    return bluez.Adapter1.new_proxy(bluez.SERVICE, path, system_bus())


async def status() -> AdapterState:
    """Adapter state, and whether the service is running at all."""
    try:
        active = (await services.status(SERVICE)).active
    except Exception:
        active = False

    if not active:
        return AdapterState(path='', service_active=False)

    adapter = await default_adapter()
    adapter.service_active = True
    return adapter


async def service_start() -> AdapterState:
    """
    Start the service, and make sure the adapter came up powered.

    bluetoothd powers the adapter at start when AutoEnable is set,
    which is the default -- but not every install keeps the default,
    and an adapter that is running but unpowered looks exactly like
    one with nothing nearby.
    """
    await services.start(SERVICE)

    adapter = await default_adapter()
    if not adapter.powered:
        await _adapter(adapter.path).powered.set_async(True)

    return await status()


async def service_stop() -> AdapterState:
    await services.stop(SERVICE)
    return await status()


# --- Devices -----------------------------------------------------------------

async def devices() -> list[bluez.Device]:
    """Every device BlueZ knows about: paired, and anything found nearby."""
    return await bluez.inventory()


async def find(address: str) -> bluez.Device:
    """
    A device by its address.

    Case-insensitive, since addresses are copied around by hand and
    BlueZ reports them in upper case while plenty of tools print lower.
    """
    wanted = address.strip().upper()
    known = await devices()

    for device in known:
        if device.address.upper() == wanted:
            return device

    raise NotFoundError('device', address, [d.address for d in known])


async def pair(address: str) -> bluez.Device:
    """
    Pair with a device and trust it.

    Long-running: it waits while someone confirms the code on both
    screens, which can take most of BlueZ's thirty seconds. Run it as
    a task.
    """
    device = await find(address)
    proxy = bluez.device_proxy(device.path)

    if not device.paired:
        try:
            await proxy.pair()
        except Exception as exc:
            raise NotAvailableError(
                f'pairing with {device.name} failed: {exc}',
                hint='put the phone in pairing mode, and confirm the code '
                     'on both screens') from exc

    await trust(address)
    return await find(address)


async def trust(address: str) -> None:
    """
    Let a paired device connect without asking.

    Without it a phone reconnecting on ignition stops to have each
    profile authorised -- the agent allows those, but it is a round
    trip per profile for nothing.
    """
    device = await find(address)
    if not device.trusted:
        await bluez.device_proxy(device.path).trusted.set_async(True)


async def forget(address: str) -> None:
    """
    Unpair and remove.

    RemoveDevice rather than just unpairing: it disconnects, drops the
    bond, and deletes the record, so the device is as if never seen. A
    phone that still believes it is paired will need to forget the car
    on its own side too before they can pair again.
    """
    device = await find(address)
    adapter = await default_adapter()
    await _adapter(adapter.path).remove_device(device.path)


async def connect(address: str) -> bluez.Device:
    device = await find(address)
    try:
        await bluez.device_proxy(device.path).connect()
    except Exception as exc:
        raise NotAvailableError(
            f'cannot connect to {device.name}: {exc}',
            hint='is it in range, with Bluetooth on?') from exc
    return await find(address)


async def disconnect(address: str) -> bluez.Device:
    device = await find(address)
    await bluez.device_proxy(device.path).disconnect()
    return await find(address)


# --- Being found, and finding -----------------------------------------------

async def set_visible(on: bool, seconds: int = 0) -> AdapterState:
    """
    Whether other devices can find the car and pair with it.

    Discoverable and pairable go together: one without the other is
    either a car nobody can see, or one everybody can see and nobody
    can pair with.

    BlueZ's own timeouts are set to the same window, so the car stops
    advertising on schedule even if whatever asked for it has died.
    """
    adapter = await default_adapter()
    proxy = _adapter(adapter.path)

    if on:
        await proxy.discoverable_timeout.set_async(seconds)
        await proxy.pairable_timeout.set_async(seconds)
        await proxy.pairable.set_async(True)
        await proxy.discoverable.set_async(True)
    else:
        await proxy.discoverable.set_async(False)
        await proxy.pairable.set_async(False)

    return await status()


async def set_discovery(on: bool) -> AdapterState:
    """
    Whether the car is looking for other devices.

    BlueZ ties discovery to the D-Bus client that started it, and
    stops it when that client goes away. So this only lasts as long as
    the calling process -- which is why pairing mode runs in the
    daemon rather than in a command that exits.
    """
    adapter = await default_adapter()
    proxy = _adapter(adapter.path)

    try:
        if on:
            await proxy.start_discovery()
        else:
            await proxy.stop_discovery()
    except Exception as exc:
        # Stopping discovery that is not running raises; that is
        # already the state asked for.
        if on:
            raise NotAvailableError(
                f'cannot start scanning: {exc}') from exc

    return await status()
