"""
Position and named locations.

    gps      where we are, via ModemManager
    places   named locations, saved in settings

Deliberately no eager imports. `gps` needs sdbus and a modem; `places`
needs neither, and something that only wants to look up "home" should
not have to have D-Bus available. Import the submodule you need:

    from carlib.location import places

GPS requires modemmanager and libqmi, plus a polkit rule for
org.freedesktop.ModemManager1 to run unprivileged.
"""

__all__ = ['gps', 'places']
