"""
The phone's contacts, kept between sessions.

Pulling a phonebook over PBAP means an OBEX transfer of every vCard
the phone holds. That is seconds for a short book and the better part
of a minute for a long one, so it cannot be what happens when a
screen opens -- the list has to be there already, and the pull has to
be something asked for.

So: a cache on disk, and a sync that replaces it. On disk rather than
in state, because the daemon holds state in memory and restarts would
mean pulling the whole book again -- which is the one thing this
exists to avoid.

One file per phone and per book. Per phone because two people with
two phones is the ordinary case in a car, and merging their contacts
would be worse than useless. Per book because PBAP serves the address
book, the favourites and three call logs through the same call, and a
single file would have a sync of the recent calls throw away the
contacts.
"""

import os
import json
import time
import hashlib
from pathlib import Path
from dataclasses import dataclass, field

from carlib.bluetooth import phonebook


# How old a cached book may be before it is worth saying so.
#
# Contacts change rarely -- a month-old address book is almost
# certainly still right, and the alternative is a minute of waiting
# on every drive.
#
# Call logs are the opposite: a list of recent calls that is an hour
# old is not a list of recent calls. Short enough that a screen
# showing one knows to refresh it, long enough not to pull on every
# glance.
STALE_SECONDS = 30 * 24 * 3600
CALL_LOG_STALE_SECONDS = 300


def _cache_dir() -> Path:
    base = os.environ.get('XDG_CACHE_HOME')
    root = Path(base) if base else Path.home() / '.cache'
    return root / 'carlib'


def _bare(address: str) -> str:
    """An address as a filename: hex only, upper case."""
    return ''.join(c for c in address.upper() if c in '0123456789ABCDEF')


def _photo_dir() -> Path:
    return _cache_dir() / 'photos'


def photo_path(digest: str) -> Path | None:
    """
    Where a photo is kept, if the digest is one we could have written.

    Checked rather than trusted: the digest reaches this from a URL,
    and a caller that could put a slash in it could read any file the
    daemon can.
    """
    if not digest or len(digest) != 32 or not all(
            c in '0123456789abcdef' for c in digest):
        return None

    path = _photo_dir() / f'{digest}.jpg'
    return path if path.is_file() else None


def _store_photo(blob: bytes) -> str:
    """
    Write a photo and return its digest.

    Content addressed: the same picture on two contacts is one file,
    and re-syncing an unchanged book rewrites nothing. It also means
    nothing has to decide when a photo has changed -- a different
    picture is simply a different name.
    """
    digest = hashlib.sha256(blob).hexdigest()[:32]
    path = _photo_dir() / f'{digest}.jpg'

    if path.exists():
        return digest

    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.tmp')
    temp.write_bytes(blob)
    temp.replace(path)
    return digest


def _path(address: str, book: str) -> Path:
    return _cache_dir() / f'phonebook-{_bare(address)}-{book}.json'


@dataclass
class Book:
    """One of a phone's books, and when it was read."""

    address: str
    # pb, fav, or one of the call logs. See phonebook.BOOKS.
    book: str = 'pb'
    contacts: list[phonebook.Contact] = field(default_factory=list)
    # Unix seconds, or 0 for a book that has never been pulled.
    fetched: float = 0.0

    @property
    def stale(self) -> bool:
        if not self.fetched:
            return False

        limit = (CALL_LOG_STALE_SECONDS if self.book in phonebook.CALL_BOOKS
                 else STALE_SECONDS)
        return time.time() - self.fetched > limit

    def to_dict(self) -> dict:
        return {
            'address': self.address,
            'book': self.book,
            'fetched': self.fetched,
            'stale': self.stale,
            'contacts': [c.to_dict() for c in self.contacts],
        }


def load(address: str, book: str = 'pb') -> Book:
    """
    A cached book for a phone.

    Empty rather than an error when there is none: a phone that has
    never been synced is the ordinary starting state, not a failure.
    """
    path = _path(address, book)

    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        return Book(address=address, book=book)

    contacts = []
    for entry in data.get('contacts') or []:
        if not isinstance(entry, dict):
            continue
        try:
            contacts.append(phonebook.Contact(
                # `or ''` rather than a default, because the default
                # only applies to a missing key. A key present with a
                # null value -- which is what a vCard field nobody
                # filled in becomes -- would otherwise give the
                # literal string 'None'.
                name=str(entry.get('name') or ''),
                numbers=[
                    phonebook.PhoneNumber(
                        number=str(n.get('number') or ''),
                        type=str(n.get('type') or ''),
                    )
                    for n in entry.get('numbers') or []
                    if isinstance(n, dict)
                ],
                emails=[str(e) for e in entry.get('emails') or [] if e],
                call_type=str(entry.get('call_type') or ''),
                photo=str(entry.get('photo') or ''),
                call_time=entry.get('call_time'),
            ))
        except (TypeError, ValueError):
            continue

    return Book(
        address=address,
        book=book,
        contacts=contacts,
        fetched=float(data.get('fetched') or 0.0),
    )


def store(book: Book) -> None:
    """
    Write a book to the cache.

    Written beside the target and moved into place, so an interrupted
    write leaves the previous book rather than half of a new one --
    the file is read at boot and a truncated one would look like a
    phone with no contacts.
    """
    path = _path(book.address, book.book)
    path.parent.mkdir(parents=True, exist_ok=True)

    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(book.to_dict(), ensure_ascii=False))
    temp.replace(path)


def forget(address: str, book: str | None = None) -> None:
    """
    Drop a phone's cache.

    One book, or all of them when none is named -- which is what
    somebody means by forgetting a phone.
    """
    books = [book] if book else list(phonebook.BOOKS)

    for which in books:
        try:
            _path(address, which).unlink()
        except OSError:
            pass


async def sync(address: str, book: str = 'pb',
               photos: bool = False) -> Book:
    """
    Pull the phonebook from the phone and cache it.

    Slow, and worth saying so at the call site: this is an OBEX
    transfer of every vCard on the device.

    The cache is left alone if the pull fails. A phone that went out
    of range mid-transfer should not cost somebody the contacts they
    already had.

    `photos` asks for pictures too, which multiplies the transfer:
    off unless somebody has asked for it.
    """
    contacts = await phonebook.fetch(address, book=book, photos=photos)

    # Out of the JSON and into their own files. A base64 blob in the
    # middle of the cache would make it megabytes and unreadable, and
    # the frontend wants a URL it can put in an img tag rather than
    # bytes it has to re-encode.
    for contact in contacts:
        if contact.photo_data:
            contact.photo = _store_photo(contact.photo_data)
            contact.photo_data = None

    fetched = Book(address=address, book=book, contacts=contacts,
                   fetched=time.time())
    store(fetched)
    return fetched
