#!/usr/bin/env python3
"""
Pull the phonebook from a paired phone over Bluetooth PBAP.

Requires obexd running on the session bus:
    systemctl --user enable --now obex

Run:
    ./bt_phonebook.py AA:BB:CC:DD:EE:FF
    ./bt_phonebook.py AA:BB:CC:DD:EE:FF --location int --book pb
    ./bt_phonebook.py AA:BB:CC:DD:EE:FF --raw out.vcf
    ./bt_phonebook.py AA:BB:CC:DD:EE:FF --json

Phonebook names: pb (contacts), ich (incoming calls), och (outgoing),
mch (missed), cch (combined calls), fav (favourites).
Locations: int (phone memory), sim1.
"""

import os
import re
import sys
import json
import asyncio
import argparse
import tempfile
from datetime import datetime, timezone

from sdbus import (
    sd_bus_open_user,
    set_default_bus,
    DbusInterfaceCommonAsync,
    dbus_method_async,
    dbus_property_async,
)


class ObexClient(DbusInterfaceCommonAsync,
                 interface_name='org.bluez.obex.Client1'):

    @dbus_method_async(input_signature='sa{sv}', result_signature='o')
    async def create_session(
            self, destination: str,
            args: dict[str, tuple[str, object]]) -> str:
        raise NotImplementedError

    @dbus_method_async(input_signature='o')
    async def remove_session(self, session: str) -> None:
        raise NotImplementedError


class PhonebookAccess(DbusInterfaceCommonAsync,
                      interface_name='org.bluez.obex.PhonebookAccess1'):

    @dbus_method_async(input_signature='ss')
    async def select(self, location: str, phonebook: str) -> None:
        raise NotImplementedError

    @dbus_method_async(input_signature='sa{sv}',
                       result_signature='oa{sv}')
    async def pull_all(
            self, target_file: str,
            filters: dict[str, tuple[str, object]],
            ) -> tuple[str, dict[str, tuple[str, object]]]:
        raise NotImplementedError

    @dbus_method_async(result_signature='q')
    async def get_size(self) -> int:
        raise NotImplementedError


class ObexTransfer(DbusInterfaceCommonAsync,
                   interface_name='org.bluez.obex.Transfer1'):

    @dbus_property_async(property_signature='s')
    def status(self) -> str:
        raise NotImplementedError

    @dbus_property_async(property_signature='t')
    def transferred(self) -> int:
        raise NotImplementedError

    @dbus_property_async(property_signature='s')
    def filename(self) -> str:
        raise NotImplementedError


def unwrap(variant):
    if isinstance(variant, tuple) and len(variant) == 2:
        return variant[1]
    return variant


def parse_irmc_datetime(raw: str) -> str | None:
    """
    IRMC basic format is 20260819T104530, optionally with a trailing Z
    for UTC. Returns an ISO 8601 string, or the raw value if unparseable.
    """
    if not raw:
        return None

    text = raw.strip()
    is_utc = text.endswith('Z')
    if is_utc:
        text = text[:-1]

    for fmt in ('%Y%m%dT%H%M%S', '%Y-%m-%dT%H:%M:%S', '%Y%m%dT%H%M'):
        try:
            dt = datetime.strptime(text, fmt)
        except ValueError:
            continue
        if is_utc:
            dt = dt.replace(tzinfo=timezone.utc).astimezone()
        return dt.isoformat(sep=' ', timespec='seconds')

    return raw


def parse_vcards(text: str) -> list[dict]:
    """Minimal vCard parser: enough for names, numbers and emails."""
    contacts = []
    current = None

    # Unfold continuation lines (RFC 6350: a leading space continues).
    text = re.sub(r'\r?\n[ \t]', '', text)

    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue

        if line.upper() == 'BEGIN:VCARD':
            current = {'name': '', 'numbers': [], 'emails': [],
                       'call_type': None, 'call_time': None}
            continue
        if line.upper() == 'END:VCARD':
            if current and (current['name'] or current['numbers']
                            or current['call_time']):
                contacts.append(current)
            current = None
            continue
        if current is None or ':' not in line:
            continue

        prop, value = line.split(':', 1)
        parts = prop.split(';')
        key = parts[0].upper()
        params = [p.upper() for p in parts[1:]]

        if key == 'FN':
            current['name'] = value.strip()
        elif key == 'N' and not current['name']:
            # N is Family;Given;Middle;Prefix;Suffix
            fields = [f.strip() for f in value.split(';')]
            family = fields[0] if len(fields) > 0 else ''
            given = fields[1] if len(fields) > 1 else ''
            current['name'] = ' '.join(p for p in (given, family) if p)
        elif key == 'TEL':
            label = next((p.split('=')[-1] for p in params
                          if 'CELL' in p or 'HOME' in p or 'WORK' in p),
                         'other')
            current['numbers'].append({
                'type': label.lower(),
                'number': value.strip(),
            })
        elif key == 'EMAIL':
            current['emails'].append(value.strip())
        elif key == 'X-IRMC-CALL-DATETIME':
            # Phones encode the direction either as a bare parameter
            # (X-IRMC-CALL-DATETIME;MISSED:...) or as TYPE=MISSED.
            for p in params:
                candidate = p.split('=')[-1]
                if candidate in ('DIALED', 'RECEIVED', 'MISSED'):
                    current['call_type'] = candidate.lower()
                    break
            current['call_time'] = parse_irmc_datetime(value.strip())
        elif key == 'X-IRMC-CALL-TYPE':
            current['call_type'] = value.strip().lower()

    return contacts


async def fetch_phonebook(address: str, location: str, book: str,
                          raw_path: str | None) -> list[dict]:
    bus = sd_bus_open_user()
    set_default_bus(bus)

    client = ObexClient.new_proxy('org.bluez.obex', '/org/bluez/obex', bus)

    # Variants are passed as (signature, value) tuples.
    session_path = await client.create_session(
        address, {'Target': ('s', 'pbap')})

    try:
        pb = PhonebookAccess.new_proxy('org.bluez.obex', session_path, bus)
        await pb.select(location, book)

        size = await pb.get_size()
        print(f'{book}@{location}: {size} entries', file=sys.stderr)

        if raw_path:
            target = os.path.abspath(raw_path)
        else:
            fd, target = tempfile.mkstemp(suffix='.vcf')
            os.close(fd)

        transfer_path, _props = await pb.pull_all(target, {})
        transfer = ObexTransfer.new_proxy(
            'org.bluez.obex', transfer_path, bus)

        # Poll until obexd reports the transfer finished. The object
        # disappears once complete, so a missing object means success.
        while True:
            try:
                state = await transfer.status
            except Exception:
                break
            if state == 'complete':
                break
            if state == 'error':
                raise RuntimeError('transfer failed')
            await asyncio.sleep(0.2)

        with open(target, 'r', encoding='utf-8', errors='replace') as fh:
            data = fh.read()

        if not raw_path:
            os.unlink(target)

        return parse_vcards(data)

    finally:
        try:
            await client.remove_session(session_path)
        except Exception:
            pass


CALL_GLYPH = {
    'received': '\U000f0b6f',   # nf-md-phone_incoming
    'dialed':   '\U000f0b74',   # nf-md-phone_outgoing
    'missed':   '\U000f0b71',   # nf-md-phone_missed
}


def print_table(contacts: list[dict]) -> None:
    if not contacts:
        print('No entries returned.')
        return

    is_call_log = any(c.get('call_time') for c in contacts)

    if is_call_log:
        # Newest first. Entries without a timestamp sink to the bottom.
        contacts = sorted(contacts,
                          key=lambda c: (c['call_time'] or ''),
                          reverse=True)
        width = max((len(c['name']) for c in contacts), default=10)
        for c in contacts:
            glyph = CALL_GLYPH.get(c.get('call_type') or '', ' ')
            number = c['numbers'][0]['number'] if c['numbers'] else '-'
            when = c['call_time'] or ''
            name = c['name'] or '(unknown)'
            print(f"{glyph}  {when:<19}  {name:<{width}}  {number}")
        print(f'\n{len(contacts)} calls', file=sys.stderr)
        return

    width = max((len(c['name']) for c in contacts), default=10)
    for c in contacts:
        numbers = ', '.join(f"{n['number']} ({n['type']})"
                            for n in c['numbers']) or '-'
        print(f"{c['name']:<{width}}  {numbers}")
    print(f'\n{len(contacts)} contacts', file=sys.stderr)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('address', help='phone MAC, e.g. AA:BB:CC:DD:EE:FF')
    ap.add_argument('--location', default='int', help='int or sim1')
    ap.add_argument('--book', default='pb',
                    help='pb, ich, och, mch, cch or fav')
    ap.add_argument('--raw', metavar='FILE',
                    help='also keep the raw .vcf at this path')
    ap.add_argument('--json', action='store_true', help='emit JSON')
    args = ap.parse_args()

    try:
        contacts = asyncio.run(fetch_phonebook(
            args.address, args.location, args.book, args.raw))
    except Exception as exc:
        print(f'error: {exc}', file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(contacts, indent=2, ensure_ascii=False))
    else:
        print_table(contacts)
    return 0


if __name__ == '__main__':
    sys.exit(main())
