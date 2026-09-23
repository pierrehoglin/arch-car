"""
The pairing agent.

Modern phones pair with Secure Simple Pairing, and BlueZ hands the
confirmation step to whichever agent is registered. With none, Pair()
fails -- and so does a phone trying to pair with the car, which is the
more common direction.

DisplayYesNo: numeric comparison. Both screens show the same six
digits and each side confirms. A car has a screen, which is what this
mode is for; Just Works (NoInputNoOutput) would pair without asking.

The agent does not decide anything itself. When BlueZ asks, it hands
the question to whoever is listening -- the daemon publishes it on the
event stream -- and holds BlueZ's call open until an answer arrives or
the wait runs out.
"""

import asyncio
import logging
from dataclasses import dataclass, asdict
from typing import Callable

from sdbus import DbusInterfaceCommonAsync, dbus_method_async
from sdbus.exceptions import DbusFailedError

from carlib.dbus import bluez
from carlib.dbus.connection import system_bus

log = logging.getLogger('carlib')

AGENT_PATH = '/carlib/agent'
CAPABILITY = 'DisplayYesNo'

# BlueZ gives up after about 30 seconds and calls Cancel. Answering
# just inside that means a slow decision is refused cleanly rather
# than racing BlueZ's own timeout.
CONFIRM_TIMEOUT = 28.0


class Rejected(DbusFailedError):
    """What BlueZ expects back when a request is refused."""

    dbus_error_name = 'org.bluez.Error.Rejected'


class Canceled(DbusFailedError):
    dbus_error_name = 'org.bluez.Error.Canceled'


@dataclass
class Request:
    """A pairing that is waiting for someone to decide."""

    device: str               # D-Bus path
    address: str
    name: str
    # Absent for Just Works, where the other side has no display and
    # there is only a yes or no to give.
    passkey: str | None = None
    kind: str = 'confirm'     # 'confirm' or 'authorize'

    def to_dict(self) -> dict:
        return asdict(self)


class Agent(DbusInterfaceCommonAsync, interface_name=bluez.IFACE_AGENT):
    """
    Exported at AGENT_PATH on the system bus.

    Method names are given explicitly rather than left to sdbus's
    snake_case conversion. BlueZ calls these by name, and a mismatch
    fails as "method not found" on the other side of the bus, with
    nothing in our own logs to say why.
    """

    def __init__(self, notify: Callable[[Request | None], None]) -> None:
        super().__init__()
        self._notify = notify
        self._pending: Request | None = None
        self._answer: asyncio.Future[bool] | None = None

    @property
    def pending(self) -> Request | None:
        return self._pending

    def answer(self, accept: bool) -> bool:
        """
        Resolve the request that is waiting.

        Returns False when there is nothing to answer, which happens
        if BlueZ gave up first -- the caller can say so rather than
        claiming the answer landed.
        """
        if self._answer is None or self._answer.done():
            return False
        self._answer.set_result(accept)
        return True

    async def _ask(self, request: Request) -> None:
        """Publish the request and wait for an answer, or refuse."""
        # A second request while one is open means BlueZ has moved on
        # from the first; the new one is the real question.
        if self._answer is not None and not self._answer.done():
            self._answer.set_result(False)

        loop = asyncio.get_running_loop()
        self._pending = request
        self._answer = loop.create_future()
        self._notify(request)

        try:
            accepted = await asyncio.wait_for(self._answer, CONFIRM_TIMEOUT)
        except asyncio.TimeoutError:
            accepted = False
        finally:
            self._pending = None
            self._answer = None
            self._notify(None)

        if not accepted:
            raise Rejected('refused')

    async def _describe(self, device: str) -> tuple[str, str]:
        """A device's address and name, for the question."""
        try:
            for known in await bluez.inventory():
                if known.path == device:
                    return known.address, known.name
        except Exception:
            pass
        return '', device.rsplit('/', 1)[-1]

    # --- What BlueZ calls ------------------------------------------------

    @dbus_method_async(input_signature='ou', method_name='RequestConfirmation')
    async def request_confirmation(self, device: str, passkey: int) -> None:
        """
        The numeric comparison: are these the same six digits?

        Zero-padded, because a passkey of 4521 is shown on the phone as
        004521, and a code that does not match what is on the phone is
        one nobody will confirm.
        """
        address, name = await self._describe(device)
        log.info('pairing: %s asks to confirm %06d', name, passkey)
        await self._ask(Request(device, address, name, f'{passkey:06d}'))

    @dbus_method_async(input_signature='o', method_name='RequestAuthorization')
    async def request_authorization(self, device: str) -> None:
        """Just Works from a device with no display: a plain yes or no."""
        address, name = await self._describe(device)
        log.info('pairing: %s asks to pair', name)
        await self._ask(Request(device, address, name, None, 'authorize'))

    @dbus_method_async(input_signature='os', method_name='AuthorizeService')
    async def authorize_service(self, device: str, uuid: str) -> None:
        """
        A paired device connecting a profile.

        Allowed without asking. Paired devices are made trusted, which
        stops BlueZ calling this at all -- it only arrives in the window
        between bonding and being trusted, and refusing there would
        break the connection the pairing was for.
        """

    @dbus_method_async(input_signature='o', result_signature='s',
                       method_name='RequestPinCode')
    async def request_pin_code(self, device: str) -> str:
        """
        Legacy pairing, from devices that predate SSP.

        Refused rather than answered with a fixed PIN. Nothing that
        would pair with a car stereo today needs it, and a hard-coded
        0000 is a PIN anyone can guess.
        """
        raise Rejected('legacy PIN pairing is not supported')

    @dbus_method_async(input_signature='o', result_signature='u',
                       method_name='RequestPasskey')
    async def request_passkey(self, device: str) -> int:
        """Asks us to type a code shown elsewhere. There is no keypad."""
        raise Rejected('passkey entry is not supported')

    @dbus_method_async(input_signature='ouq', method_name='DisplayPasskey')
    async def display_passkey(self, device: str, passkey: int,
                              entered: int) -> None:
        log.info('pairing: passkey %06d (%d typed)', passkey, entered)

    @dbus_method_async(input_signature='os', method_name='DisplayPinCode')
    async def display_pin_code(self, device: str, pincode: str) -> None:
        log.info('pairing: PIN %s', pincode)

    @dbus_method_async(method_name='Cancel')
    async def cancel(self) -> None:
        """BlueZ has given up on the request -- the other side left."""
        if self._answer is not None and not self._answer.done():
            self._answer.set_result(False)

    @dbus_method_async(method_name='Release')
    async def release(self) -> None:
        """Unregistered by BlueZ, usually because bluetoothd stopped."""
        log.info('pairing: agent released')


async def register(agent: Agent) -> None:
    """
    Export the agent and make it the default.

    Default, so it answers pairings the phone starts as well as ones
    the car does. Safe to call again after bluetoothd restarts, which
    forgets every registered agent.
    """
    bus = system_bus()

    # Exporting twice on the same path raises, so only the first call
    # does it. Registration with BlueZ is what has to be repeated.
    if not getattr(agent, '_exported', False):
        agent.export_to_dbus(AGENT_PATH, bus)
        agent._exported = True

    manager = bluez.agent_manager()

    try:
        await manager.register_agent(AGENT_PATH, CAPABILITY)
    except Exception as exc:
        # Already registered with this bluetoothd -- nothing to redo.
        # Tolerated rather than tracked: the only way to know a
        # restart has wiped the registration is to try, and trying is
        # cheap.
        if 'AlreadyExists' not in f'{type(exc).__name__} {exc}':
            raise
        return

    await manager.request_default_agent(AGENT_PATH)
    log.info('pairing: agent registered (%s)', CAPABILITY)
