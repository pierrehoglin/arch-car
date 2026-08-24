"""
Position: GPS via ModemManager, with cell-tower fallback.

Requires modemmanager and libqmi, plus a polkit rule for
org.freedesktop.ModemManager1 if you want to run unprivileged.
"""

from carlib.location import gps

__all__ = ['gps']
