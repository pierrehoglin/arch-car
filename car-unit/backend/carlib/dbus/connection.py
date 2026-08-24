"""
Bus connections.

A CLI opens a bus, does one thing and exits. A long-running API should
hold one connection per bus for its whole life -- reconnecting per
request is wasteful and breaks signal subscriptions.

Both are served by caching here. Call `system_bus()` / `session_bus()`
freely; you get the same object back.
"""

from sdbus import sd_bus_open_system, sd_bus_open_user, set_default_bus

from carlib.core.errors import NotAvailableError

_system = None
_session = None


def system_bus():
    """The system bus, where BlueZ and oFono live."""
    global _system
    if _system is None:
        try:
            _system = sd_bus_open_system()
        except Exception as exc:
            raise NotAvailableError(
                f'cannot open the system bus: {exc}') from exc
        set_default_bus(_system)
    return _system


def session_bus():
    """
    The session bus, where obexd lives.

    Needs XDG_RUNTIME_DIR and DBUS_SESSION_BUS_ADDRESS in the
    environment -- fine in a desktop session, but a systemd system
    service will not have them.
    """
    global _session
    if _session is None:
        try:
            _session = sd_bus_open_user()
        except Exception as exc:
            raise NotAvailableError(
                f'cannot open the session bus: {exc}',
                hint='obexd runs on the session bus; a system service '
                     'needs DBUS_SESSION_BUS_ADDRESS set, or run this '
                     'as a user unit.') from exc
        set_default_bus(_session)
    return _session


def reset() -> None:
    """
    Drop cached connections.

    Mostly for tests. A daemon should not need this -- sdbus reconnects
    internally if the bus restarts.
    """
    global _system, _session
    _system = None
    _session = None
