"""
MAP: SMS and MMS.

Signatures here were taken from `busctl --user introspect` against a
live session -- they differ across BlueZ versions, so if a method errors
with "doesn't exist", introspect and compare.

MAP treats folders as a filesystem you navigate with SetFolder, then
list the current folder with an empty name. Passing a path straight to
ListMessages is what most phones reject with "Bad Request".
"""

import os
import tempfile
from dataclasses import dataclass, asdict

from sdbus import DbusInterfaceCommonAsync, dbus_method_async

from carlib.dbus import obex
from carlib.dbus.connection import session_bus
from carlib.dbus.variants import props

FOLDERS = ('inbox', 'sent', 'outbox', 'draft', 'deleted')


class MessageAccess1(DbusInterfaceCommonAsync,
                     interface_name='org.bluez.obex.MessageAccess1'):

    @dbus_method_async(input_signature='s')
    async def set_folder(self, name: str) -> None:
        raise NotImplementedError

    @dbus_method_async(input_signature='a{sv}', result_signature='aa{sv}')
    async def list_folders(self, filters: dict) -> list[dict]:
        raise NotImplementedError

    @dbus_method_async(input_signature='sa{sv}',
                       result_signature='a{oa{sv}}')
    async def list_messages(self, folder: str,
                            filters: dict) -> dict[str, dict]:
        raise NotImplementedError

    @dbus_method_async(result_signature='as')
    async def list_filter_fields(self) -> list[str]:
        raise NotImplementedError

    @dbus_method_async(input_signature='ssa{sv}', result_signature='oa{sv}')
    async def push_message(self, source_file: str, folder: str,
                           args: dict) -> tuple[str, dict]:
        raise NotImplementedError

    @dbus_method_async()
    async def update_inbox(self) -> None:
        raise NotImplementedError


class Message1(DbusInterfaceCommonAsync,
               interface_name='org.bluez.obex.Message1'):

    @dbus_method_async(input_signature='sb', result_signature='oa{sv}')
    async def get(self, target_file: str,
                  attachment: bool) -> tuple[str, dict]:
        raise NotImplementedError


@dataclass
class MessageHeader:
    handle: str
    subject: str = ''
    timestamp: str = ''
    sender: str = ''
    sender_number: str = ''
    recipient: str = ''
    type: str = ''
    read: bool = False
    sent: bool = False

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def who(self) -> str:
        return self.sender or self.sender_number or self.recipient or '?'


@dataclass
class MessageBody:
    sender: str = ''
    sender_number: str = ''
    body: str = ''
    status: str = ''

    def to_dict(self) -> dict:
        return asdict(self)


def parse_bmessage(text: str) -> MessageBody:
    """
    bMessage is MAP's container format: nested BEGIN/END blocks with the
    actual text inside BEGIN:MSG ... END:MSG.
    """
    result = MessageBody()
    in_body = False
    body_lines: list[str] = []

    for line in text.splitlines():
        stripped = line.strip()
        upper = stripped.upper()

        if upper == 'BEGIN:MSG':
            in_body = True
            continue
        if upper == 'END:MSG':
            in_body = False
            continue
        if in_body:
            body_lines.append(line)
            continue

        if ':' not in stripped:
            continue
        key, value = stripped.split(':', 1)
        key = key.split(';')[0].upper()

        if key == 'N' and not result.sender:
            result.sender = value.split(';')[0].strip()
        elif key == 'FN' and not result.sender:
            result.sender = value.strip()
        elif key == 'TEL':
            result.sender_number = value.strip()
        elif key == 'STATUS':
            result.status = value.strip()

    result.body = '\n'.join(body_lines).strip()
    return result


def build_bmessage(number: str, text: str,
                   folder: str = 'telecom/msg/outbox') -> str:
    """Minimal bMessage for PushMessage."""
    body = f'BEGIN:MSG\r\n{text}\r\nEND:MSG\r\n'
    return (
        'BEGIN:BMSG\r\n'
        'VERSION:1.0\r\n'
        'STATUS:UNREAD\r\n'
        'TYPE:SMS_GSM\r\n'
        f'FOLDER:{folder}\r\n'
        'BEGIN:VCARD\r\n'
        'VERSION:2.1\r\n'
        f'TEL:{number}\r\n'
        'END:VCARD\r\n'
        'BEGIN:BENV\r\n'
        'BEGIN:BBODY\r\n'
        'CHARSET:UTF-8\r\n'
        f'LENGTH:{len(body)}\r\n'
        f'{body}'
        'END:BBODY\r\n'
        'END:BENV\r\n'
        'END:BMSG\r\n'
    )


async def _navigate(mas: MessageAccess1, folder: str) -> None:
    """Walk to telecom/msg/<folder> from the root."""
    await mas.set_folder('/')
    await mas.set_folder('telecom')
    await mas.set_folder('msg')
    await mas.set_folder(folder)


async def folders(address: str) -> list[str]:
    async with obex.session(address, 'map') as sess:
        mas = MessageAccess1.new_proxy(obex.SERVICE, sess, session_bus())
        raw = await mas.list_folders({})
        return [props(f).get('Name', '?') for f in raw]


async def filter_fields(address: str) -> list[str]:
    async with obex.session(address, 'map') as sess:
        mas = MessageAccess1.new_proxy(obex.SERVICE, sess, session_bus())
        return await mas.list_filter_fields()


async def listing(address: str, folder: str = 'inbox',
                  count: int = 25) -> list[MessageHeader]:
    """Message headers from a folder, newest first."""
    async with obex.session(address, 'map') as sess:
        mas = MessageAccess1.new_proxy(obex.SERVICE, sess, session_bus())
        await _navigate(mas, folder)

        filters = {'MaxCount': ('q', count)} if count else {}
        raw = await mas.list_messages('', filters)

    headers = []
    for path, raw_props in raw.items():
        p = props(raw_props)
        headers.append(MessageHeader(
            handle=path,
            subject=p.get('Subject', ''),
            timestamp=p.get('Timestamp', ''),
            sender=p.get('Sender', ''),
            sender_number=p.get('SenderAddress', ''),
            recipient=p.get('Recipient', ''),
            type=p.get('Type', ''),
            read=bool(p.get('Read', False)),
            sent=bool(p.get('Sent', False)),
        ))

    headers.sort(key=lambda m: m.timestamp, reverse=True)
    return headers


async def read(address: str, handle: str,
               keep_raw: str | None = None) -> MessageBody:
    """
    Fetch one message body.

    The session must be open for the handle to resolve, which is why the
    address is needed even though the handle looks self-contained.
    """
    async with obex.session(address, 'map'):
        msg = Message1.new_proxy(obex.SERVICE, handle, session_bus())

        async with obex.scratch_file(keep_raw, '.bmsg') as target:
            transfer_path, _ = await msg.get(target, False)
            await obex.await_transfer(transfer_path)
            return parse_bmessage(obex.read_text(target))


async def send(address: str, number: str, text: str) -> None:
    """
    Send an SMS via PushMessage.

    Support varies: some phones accept the push and never transmit.
    Check the phone's own outbox after calling this.
    """
    fd, path = tempfile.mkstemp(suffix='.bmsg')
    with os.fdopen(fd, 'w', encoding='utf-8') as fh:
        fh.write(build_bmessage(number, text))

    try:
        async with obex.session(address, 'map') as sess:
            mas = MessageAccess1.new_proxy(
                obex.SERVICE, sess, session_bus())
            transfer_path, _ = await mas.push_message(
                path, 'telecom/msg/outbox', {})
            await obex.await_transfer(transfer_path)
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


async def update_inbox(address: str) -> None:
    """Ask the phone to refresh its inbox before listing."""
    async with obex.session(address, 'map') as sess:
        mas = MessageAccess1.new_proxy(obex.SERVICE, sess, session_bus())
        await mas.update_inbox()
