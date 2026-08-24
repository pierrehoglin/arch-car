"""
D-Bus plumbing and interface declarations.

Interfaces are grouped by the service that owns them, because that is
how they version: when BlueZ changes a signature you edit bluez.py.

sdbus raises ValueError if an interface name is declared twice in one
process, so each must be declared exactly once, here.
"""

from carlib.dbus.connection import system_bus, session_bus, reset
from carlib.dbus.variants import unwrap, props, as_variant

__all__ = [
    'system_bus',
    'session_bus',
    'reset',
    'unwrap',
    'props',
    'as_variant',
]
