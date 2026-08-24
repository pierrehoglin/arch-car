#!/usr/bin/env python3
"""
Read SMS/MMS over Bluetooth MAP (Message Access Profile) via obexd.

MAP is separate from HFP: oFono handles calls, obexd handles messages.
Requires obexd on the session bus:
    systemctl --user enable --now obex

The phone must grant message access for this device -- on Android that
is a per-device toggle in Bluetooth settings, usually next to the
contact-sharing one. Without it CreateSession is refused.

Run:
    ./bt_messages.py AA:BB:CC:DD:EE:FF folders        # list folders
    ./bt_messages.py AA:BB:CC:DD:EE:FF filters        # supported filters
    ./bt_messages.py AA:BB:CC:DD:EE:FF list           # inbox headers
    ./bt_messages.py AA:BB:CC:DD:EE:FF list --folder sent
    ./bt_messages.py AA:BB:CC:DD:EE:FF list --count 50 --json
    ./bt_messages.py AA:BB:CC:DD:EE:FF read <handle>  # full message body
    ./bt_messages.py AA:BB:CC:DD:EE:FF send +4670... 'text'

Signatures here were taken from `busctl --user introspect` against a
live session -- they differ between BlueZ versions, so if a method
errors with "doesn't exist", introspect and compare.

Sending is the least reliable part: some phones accept the push and
never transmit. Check the phone's own outbox after trying.
"""

import os
import sys
import json
import asyncio
import argparse
import tempfile

from sdbus import (
    sd_bus_open_user,
    set_default_bus,
    DbusInterfaceCommonAsync,
    dbus_method_async,
    dbus_property_async,
)

OBEX = 'org.bluez.obex'


class ObexClient(DbusInterfaceCommonAsync,
                 interface_name='org.bluez.obex.Client1'):

    @dbus_method_async(input_signature='sa{sv}', result_signature='o')
    async def create_session(self, destination: str,
                             args: dict) -> str:
        raise NotImplementedError

    @dbus_method_async(input_signature='o')
    async def remove_session(self, session: str) -> None:
        raise NotImplementedError


class MessageAccess(DbusInterfaceCommonAsync,
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

    @dbus_method_async(input_signature='ssa{sv}',
                       result_signature='oa{sv}')
    async def push_message(self, source_file: str, folder: str,
                           args: dict) -> tuple[str, dict]:
        raise NotImplementedError

    @dbus_method_async()
    async def update_inbox(self) -> None:
        raise NotImplementedError


class Message(DbusInterfaceCommonAsync,
              interface_name='org.bluez.obex.Message1'):

    @dbus_method_async(input_signature='sb', result_signature='oa{sv}')
    async def get(self, target_file: str,
                  attachment: bool) -> tuple[str, dict]:
        raise NotImplementedError


class ObexTransfer(DbusInterfaceCommonAsync,
                   interface_name='org.bluez.obex.Transfer1'):

    @dbus_property_async(property_signature='s')
    def status(self) -> str:
        raise NotImplementedError


def unwrap(variant):
    if isinstance(variant, tuple) and len(variant) == 2:
        return variant[1]
    return variant


def props(raw: dict) -> dict:
    return {k: unwrap(v) for k, v in (raw or {}).items()}


async def open_session(bus, address: str) -> str:
    client = ObexClient.new_proxy(OBEX, '/org/bluez/obex', bus)
    return await client.create_session(address, {'Target': ('s', 'map')})


async def close_session(bus, session: str) -> None:
    try:
        client = ObexClient.new_proxy(OBEX, '/org/bluez/obex', bus)
        await client.remove_session(session)
    except Exception:
        pass


async def await_transfer(bus, transfer_path: str) -> None:
    transfer = ObexTransfer.new_proxy(OBEX, transfer_path, bus)
    while True:
        try:
            state = await transfer.status
        except Exception:
            return          # object gone == complete
        if state == 'complete':
            return
        if state == 'error':
            raise RuntimeError('transfer failed')
        await asyncio.sleep(0.2)


def parse_bmessage(text: str) -> dict:
    """
    bMessage is the MAP container format: nested BEGIN/END blocks with
    the actual body inside BEGIN:MSG ... END:MSG.
    """
    result = {'sender': '', 'sender_number': '', 'body': '', 'status': ''}
    in_body = False
    body_lines = []

    for line in text.splitlines():
        stripped = line.strip()

        if stripped.upper() == 'BEGIN:MSG':
            in_body = True
            continue
        if stripped.upper() == 'END:MSG':
            in_body = False
            continue
        if in_body:
            body_lines.append(line)
            continue

        if ':' not in stripped:
            continue
        key, value = stripped.split(':', 1)
        key = key.split(';')[0].upper()

        if key == 'N' and not result['sender']:
            result['sender'] = value.split(';')[0].strip()
        elif key == 'FN' and not result['sender']:
            result['sender'] = value.strip()
        elif key == 'TEL':
            result['sender_number'] = value.strip()
        elif key == 'STATUS':
            result['status'] = value.strip()

    result['body'] = '\n'.join(body_lines).strip()
    return result


# --- Commands --------------------------------------------------------------

async def cmd_folders(address: str) -> None:
    bus = sd_bus_open_user()
    set_default_bus(bus)

    session = await open_session(bus, address)
    try:
        mas = MessageAccess.new_proxy(OBEX, session, bus)
        folders = await mas.list_folders({})
        if not folders:
            print('No folders returned.')
            return
        for raw in folders:
            p = props(raw)
            print(p.get('Name', '?'))
    finally:
        await close_session(bus, session)


async def cmd_list(address: str, folder: str, count: int,
                   as_json: bool) -> None:
    bus = sd_bus_open_user()
    set_default_bus(bus)

    session = await open_session(bus, address)
    try:
        mas = MessageAccess.new_proxy(OBEX, session, bus)

        # Navigate to the folder first, then list the current one with an
        # empty name -- passing a path to ListMessages is what most
        # phones reject with "Bad Request".
        await mas.set_folder('/')
        await mas.set_folder('telecom')
        await mas.set_folder('msg')
        await mas.set_folder(folder)

        filters = {'MaxCount': ('q', count)} if count else {}
        messages = await mas.list_messages('', filters)

        parsed = []
        for path, raw in messages.items():
            p = props(raw)
            parsed.append({
                'handle':        path,
                'subject':       p.get('Subject', ''),
                'timestamp':     p.get('Timestamp', ''),
                'sender':        p.get('Sender', ''),
                'sender_number': p.get('SenderAddress', ''),
                'recipient':     p.get('Recipient', ''),
                'type':          p.get('Type', ''),
                'read':          bool(p.get('Read', False)),
                'sent':          bool(p.get('Sent', False)),
            })

        parsed.sort(key=lambda m: m['timestamp'], reverse=True)

        if as_json:
            print(json.dumps(parsed, indent=2, ensure_ascii=False))
            return

        if not parsed:
            print(f'No messages in {folder}.')
            return

        for m in parsed:
            mark = ' ' if m['read'] else '*'
            who = m['sender'] or m['sender_number'] or m['recipient'] or '?'
            print(f"{mark} {m['timestamp']:<16} {who:<22} "
                  f"{m['subject'][:50]}")
            print(f"    {m['handle']}")
        print(f'\n{len(parsed)} messages in {folder}', file=sys.stderr)

    finally:
        await close_session(bus, session)


async def cmd_read(address: str, handle: str, raw_path: str | None) -> None:
    bus = sd_bus_open_user()
    set_default_bus(bus)

    session = await open_session(bus, address)
    try:
        msg = Message.new_proxy(OBEX, handle, bus)

        if raw_path:
            target = os.path.abspath(raw_path)
        else:
            fd, target = tempfile.mkstemp(suffix='.bmsg')
            os.close(fd)

        transfer_path, _ = await msg.get(target, False)
        await await_transfer(bus, transfer_path)

        with open(target, 'r', encoding='utf-8', errors='replace') as fh:
            data = fh.read()

        if not raw_path:
            os.unlink(target)

        parsed = parse_bmessage(data)
        who = parsed['sender'] or parsed['sender_number'] or 'unknown'
        print(f"from: {who}")
        if parsed['status']:
            print(f"status: {parsed['status']}")
        print()
        print(parsed['body'])

    finally:
        await close_session(bus, session)


async def cmd_filters(address: str) -> None:
    """Which filter fields this phone supports for ListMessages."""
    bus = sd_bus_open_user()
    set_default_bus(bus)

    session = await open_session(bus, address)
    try:
        mas = MessageAccess.new_proxy(OBEX, session, bus)
        for field in await mas.list_filter_fields():
            print(field)
    finally:
        await close_session(bus, session)


async def cmd_send(address: str, number: str, text: str) -> None:
    """
    Send an SMS by pushing a bMessage to the outbox. Support varies --
    some phones accept the push but never transmit.
    """
    bus = sd_bus_open_user()
    set_default_bus(bus)

    bmsg = (
        'BEGIN:BMSG\r\n'
        'VERSION:1.0\r\n'
        'STATUS:UNREAD\r\n'
        'TYPE:SMS_GSM\r\n'
        'FOLDER:telecom/msg/outbox\r\n'
        'BEGIN:VCARD\r\n'
        'VERSION:2.1\r\n'
        f'TEL:{number}\r\n'
        'END:VCARD\r\n'
        'BEGIN:BENV\r\n'
        'BEGIN:BBODY\r\n'
        'CHARSET:UTF-8\r\n'
        f'LENGTH:{len(text) + 22}\r\n'
        'BEGIN:MSG\r\n'
        f'{text}\r\n'
        'END:MSG\r\n'
        'END:BBODY\r\n'
        'END:BENV\r\n'
        'END:BMSG\r\n'
    )

    fd, path = tempfile.mkstemp(suffix='.bmsg')
    with os.fdopen(fd, 'w', encoding='utf-8') as fh:
        fh.write(bmsg)

    session = await open_session(bus, address)
    try:
        mas = MessageAccess.new_proxy(OBEX, session, bus)
        transfer_path, _ = await mas.push_message(
            path, 'telecom/msg/outbox', {})
        await await_transfer(bus, transfer_path)
        print(f'sent to {number}')
    finally:
        os.unlink(path)
        await close_session(bus, session)


# --- Entry point -----------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(
        description='Read SMS/MMS over Bluetooth MAP via obexd.')
    ap.add_argument('address', help='phone MAC, e.g. AA:BB:CC:DD:EE:FF')
    sub = ap.add_subparsers(dest='cmd', required=True)

    sub.add_parser('folders', help='list message folders')
    sub.add_parser('filters', help='filter fields this phone supports')

    lst = sub.add_parser('list', help='list message headers')
    lst.add_argument('--folder', default='inbox',
                     help='inbox, sent, outbox, draft, deleted')
    lst.add_argument('--count', type=int, default=25,
                     help='max messages to fetch (0 = no limit)')
    lst.add_argument('--json', action='store_true')

    rd = sub.add_parser('read', help='fetch one message body')
    rd.add_argument('handle', help='object path from `list`')
    rd.add_argument('--raw', metavar='FILE',
                    help='also keep the raw bMessage at this path')

    snd = sub.add_parser('send', help='send an SMS (support varies)')
    snd.add_argument('number')
    snd.add_argument('text')

    args = ap.parse_args()

    try:
        if args.cmd == 'folders':
            asyncio.run(cmd_folders(args.address))
        elif args.cmd == 'filters':
            asyncio.run(cmd_filters(args.address))
        elif args.cmd == 'list':
            asyncio.run(cmd_list(args.address, args.folder,
                                 args.count, args.json))
        elif args.cmd == 'read':
            asyncio.run(cmd_read(args.address, args.handle, args.raw))
        elif args.cmd == 'send':
            asyncio.run(cmd_send(args.address, args.number, args.text))
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        print(f'error: {exc}', file=sys.stderr)
        return 1

    return 0


if __name__ == '__main__':
    sys.exit(main())
