"""
Transport-agnostic helpers.

Nothing here imports D-Bus, socketcan or any other transport -- that is
the point. A CAN-only process should be able to import `carlib.core`
without pulling in sdbus.
"""

from carlib.core.errors import (
    CarError,
    NotFoundError,
    AmbiguousMatchError,
    TransferError,
    NotAvailableError,
)
from carlib.core.match import select, select_optional

__all__ = [
    'CarError',
    'NotFoundError',
    'AmbiguousMatchError',
    'TransferError',
    'NotAvailableError',
    'select',
    'select_optional',
]
