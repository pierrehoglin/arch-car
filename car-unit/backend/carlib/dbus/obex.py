"""
OBEX sessions, shared by PBAP (phonebook) and MAP (messages).

The session/transfer dance was duplicated in both scripts. Here it is
once, wrapped in an async context manager so callers cannot leak a
session by forgetting a finally block.
"""

import os
import asyncio
import tempfile
from contextlib import asynccontextmanager

from sdbus import (
    DbusInterfaceCommonAsync,
    dbus_method_async,
    dbus_property_async,
)

from carlib.dbus.connection import session_bus
from carlib.core.errors import NotAvailableError, TransferError

SERVICE = 'org.bluez.obex'
ROOT = '/org/bluez/obex'

TRANSFER_TIMEOUT = 60.0
POLL_INTERVAL = 0.2


class Client1(DbusInterfaceCommonAsync,
              interface_name='org.bluez.obex.Client1'):

    @dbus_method_async(input_signature='sa{sv}', result_signature='o')
    async def create_session(self, destination: str, args: dict) -> str:
        raise NotImplementedError

    @dbus_method_async(input_signature='o')
    async def remove_session(self, session: str) -> None:
        raise NotImplementedError


class Transfer1(DbusInterfaceCommonAsync,
                interface_name='org.bluez.obex.Transfer1'):

    @dbus_property_async(property_signature='s')
    def status(self) -> str:
        raise NotImplementedError

    @dbus_property_async(property_signature='t')
    def transferred(self) -> int:
        raise NotImplementedError


def client() -> Client1:
    return Client1.new_proxy(SERVICE, ROOT, session_bus())


@asynccontextmanager
async def session(address: str, target: str):
    """
    Open an OBEX session and guarantee it is removed.

        async with session(mac, 'pbap') as path:
            pb = PhonebookAccess1.new_proxy(SERVICE, path, session_bus())

    target is 'pbap' for contacts or 'map' for messages.
    """
    bus = session_bus()
    c = Client1.new_proxy(SERVICE, ROOT, bus)

    try:
        path = await c.create_session(address, {'Target': ('s', target)})
    except Exception as exc:
        raise NotAvailableError(
            f'cannot open a {target.upper()} session to {address}: {exc}',
            hint=f'check obexd is running (systemctl --user status obex), '
                 f'the phone is connected, and that {target.upper()} '
                 f'access is granted for this device in the phone\'s '
                 f'Bluetooth settings.') from exc

    try:
        yield path
    finally:
        try:
            await c.remove_session(path)
        except Exception:
            pass        # session may already be gone; nothing to salvage


async def await_transfer(transfer_path: str,
                         timeout: float = TRANSFER_TIMEOUT) -> None:
    """
    Block until an OBEX transfer completes.

    obexd usually destroys the transfer object on completion, so a
    failing property read counts as success rather than an error.
    """
    transfer = Transfer1.new_proxy(SERVICE, transfer_path, session_bus())
    waited = 0.0

    while waited < timeout:
        try:
            state = await transfer.status
        except Exception:
            return
        if state == 'complete':
            return
        if state == 'error':
            raise TransferError(f'transfer failed: {transfer_path}')
        await asyncio.sleep(POLL_INTERVAL)
        waited += POLL_INTERVAL

    raise TransferError(
        f'transfer timed out after {timeout:.0f}s: {transfer_path}')


@asynccontextmanager
async def scratch_file(keep_at: str | None = None, suffix: str = '.tmp'):
    """
    A path obexd can write to, cleaned up unless the caller wants it.

    OBEX pulls write to a file rather than returning bytes, so every
    fetch needs one of these.
    """
    if keep_at:
        path = os.path.abspath(keep_at)
        yield path
        return

    fd, path = tempfile.mkstemp(suffix=suffix)
    os.close(fd)
    try:
        yield path
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


def read_text(path: str) -> str:
    with open(path, 'r', encoding='utf-8', errors='replace') as fh:
        return fh.read()
