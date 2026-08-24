"""
Exception types.

These are deliberately coarse and map onto HTTP status codes when this
library sits behind an API:

    NotFoundError        -> 404
    AmbiguousMatchError  -> 409
    NotAvailableError    -> 503
    TransferError        -> 502
    CarError             -> 500
"""


class CarError(Exception):
    """Base for everything this library raises."""


class NotFoundError(CarError):
    """No device / modem / player matched."""

    def __init__(self, what: str, match: str, available: list[str]):
        self.what = what
        self.match = match
        self.available = available
        known = ', '.join(available) if available else 'none connected'
        super().__init__(f'no {what} matching {match!r}; have: {known}')


class AmbiguousMatchError(CarError):
    """More than one candidate matched."""

    def __init__(self, what: str, match: str, hits: list[str]):
        self.what = what
        self.match = match
        self.hits = hits
        super().__init__(
            f'{match!r} matches more than one {what}: ' + ', '.join(hits))


class NotAvailableError(CarError):
    """
    The service or interface isn't there.

    Usually means a daemon is not running, a profile is not connected, or
    the phone has not granted access.
    """

    def __init__(self, message: str, hint: str | None = None):
        self.hint = hint
        super().__init__(f'{message}\n{hint}' if hint else message)


class TransferError(CarError):
    """An OBEX transfer failed or timed out."""
