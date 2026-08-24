"""
carlib -- integration library for the car unit.

Everything is async, returns dataclasses, and raises typed exceptions
from `carlib.core.errors`. Nothing prints or exits, so the same calls
back both the CLI tools and an HTTP API.

Layout follows two axes -- transport and domain:

    core/       transport-agnostic: errors, matching, output helpers
    dbus/       D-Bus plumbing and interface declarations
    bluetooth/  calls, media, phonebook, messages  (via D-Bus)
    location/   GPS and cell position               (via D-Bus)
    vehicle/    CAN bus, OBD-II                     (via socketcan)

Domain modules do not care which transport they use; that is what
keeps `vehicle/` from dragging D-Bus in.

Typical use:

    from carlib.bluetooth import calls, media
    from carlib.location import gps
    from carlib.core.errors import NotFoundError

    fix = await gps.get()
    await calls.dial('+46701234567')
"""

from carlib.core.errors import (
    CarError,
    NotFoundError,
    AmbiguousMatchError,
    TransferError,
    NotAvailableError,
)

__version__ = '0.1.0'

__all__ = [
    'CarError',
    'NotFoundError',
    'AmbiguousMatchError',
    'TransferError',
    'NotAvailableError',
]
