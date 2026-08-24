"""
PBAP: contacts and call logs.

Phonebook names:
    pb   contacts        ich  incoming calls
    fav  favourites      och  outgoing calls
                         mch  missed calls
                         cch  all calls combined

Locations: 'int' (phone memory) or 'sim1'.
"""

import re
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone

from sdbus import DbusInterfaceCommonAsync, dbus_method_async

from carlib.dbus import obex
from carlib.dbus.connection import session_bus

BOOKS = ('pb', 'ich', 'och', 'mch', 'cch', 'fav')
LOCATIONS = ('int', 'sim1')

CALL_BOOKS = ('ich', 'och', 'mch', 'cch')


class PhonebookAccess1(DbusInterfaceCommonAsync,
                       interface_name='org.bluez.obex.PhonebookAccess1'):

    @dbus_method_async(input_signature='ss')
    async def select(self, location: str, phonebook: str) -> None:
        raise NotImplementedError

    @dbus_method_async(input_signature='sa{sv}', result_signature='oa{sv}')
    async def pull_all(self, target_file: str,
                       filters: dict) -> tuple[str, dict]:
        raise NotImplementedError

    @dbus_method_async(result_signature='q')
    async def get_size(self) -> int:
        raise NotImplementedError

    @dbus_method_async(result_signature='as')
    async def list_filter_fields(self) -> list[str]:
        raise NotImplementedError


@dataclass
class PhoneNumber:
    number: str
    type: str = 'other'


@dataclass
class Contact:
    name: str = ''
    numbers: list[PhoneNumber] = field(default_factory=list)
    emails: list[str] = field(default_factory=list)
    call_type: str | None = None      # received / dialed / missed
    call_time: str | None = None      # ISO 8601, local time

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def is_call(self) -> bool:
        return self.call_time is not None

    @property
    def primary_number(self) -> str:
        return self.numbers[0].number if self.numbers else ''


def parse_irmc_datetime(raw: str) -> str | None:
    """
    IRMC basic format is 20260819T104530, optionally with a trailing Z
    for UTC. Returns ISO 8601 in local time, or the raw value if it does
    not parse -- losing a timestamp is worse than showing an odd one.
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


def parse_vcards(text: str) -> list[Contact]:
    """
    Enough vCard for names, numbers, emails and call-log metadata.

    Not a general parser: no photos, no structured addresses, no
    quoted-printable decoding.
    """
    contacts: list[Contact] = []
    current: Contact | None = None

    # RFC 6350 line folding: a leading space continues the previous line.
    text = re.sub(r'\r?\n[ \t]', '', text)

    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue

        upper = line.upper()
        if upper == 'BEGIN:VCARD':
            current = Contact()
            continue
        if upper == 'END:VCARD':
            if current and (current.name or current.numbers
                            or current.call_time):
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
            current.name = value.strip()
        elif key == 'N' and not current.name:
            fields = [f.strip() for f in value.split(';')]
            family = fields[0] if fields else ''
            given = fields[1] if len(fields) > 1 else ''
            current.name = ' '.join(p for p in (given, family) if p)
        elif key == 'TEL':
            label = next((p.split('=')[-1] for p in params
                          if 'CELL' in p or 'HOME' in p or 'WORK' in p),
                         'other')
            current.numbers.append(
                PhoneNumber(number=value.strip(), type=label.lower()))
        elif key == 'EMAIL':
            current.emails.append(value.strip())
        elif key == 'X-IRMC-CALL-DATETIME':
            # Direction arrives either as a bare parameter (;MISSED:) or
            # as TYPE=MISSED, depending on the phone.
            for p in params:
                candidate = p.split('=')[-1]
                if candidate in ('DIALED', 'RECEIVED', 'MISSED'):
                    current.call_type = candidate.lower()
                    break
            current.call_time = parse_irmc_datetime(value.strip())
        elif key == 'X-IRMC-CALL-TYPE':
            current.call_type = value.strip().lower()

    return contacts


async def fetch(address: str,
                book: str = 'pb',
                location: str = 'int',
                keep_raw: str | None = None) -> list[Contact]:
    """
    Pull a phonebook or call log from the phone.

    Call logs come back newest first; contacts sorted by name.
    """
    async with obex.session(address, 'pbap') as sess:
        pb = PhonebookAccess1.new_proxy(obex.SERVICE, sess, session_bus())
        await pb.select(location, book)

        async with obex.scratch_file(keep_raw, '.vcf') as target:
            transfer_path, _ = await pb.pull_all(target, {})
            await obex.await_transfer(transfer_path)
            contacts = parse_vcards(obex.read_text(target))

    if book in CALL_BOOKS:
        contacts.sort(key=lambda c: c.call_time or '', reverse=True)
    else:
        contacts.sort(key=lambda c: c.name.lower())

    return contacts


async def size(address: str, book: str = 'pb',
               location: str = 'int') -> int:
    """Entry count without pulling the whole book."""
    async with obex.session(address, 'pbap') as sess:
        pb = PhonebookAccess1.new_proxy(obex.SERVICE, sess, session_bus())
        await pb.select(location, book)
        return await pb.get_size()


async def filter_fields(address: str) -> list[str]:
    """Which vCard fields this phone can filter on."""
    async with obex.session(address, 'pbap') as sess:
        pb = PhonebookAccess1.new_proxy(obex.SERVICE, sess, session_bus())
        return await pb.list_filter_fields()


def index_by_number(contacts: list[Contact]) -> dict[str, str]:
    """
    Reverse-lookup table for caller ID.

    Keyed on the last 7 digits so that +46701234567, 0701234567 and
    070-123 45 67 all resolve to the same contact.
    """
    index: dict[str, str] = {}
    for c in contacts:
        if not c.name:
            continue
        for num in c.numbers:
            digits = re.sub(r'\D', '', num.number)
            if len(digits) >= 7:
                index[digits[-7:]] = c.name
    return index


def lookup_number(index: dict[str, str], number: str) -> str | None:
    digits = re.sub(r'\D', '', number or '')
    if len(digits) < 7:
        return None
    return index.get(digits[-7:])
