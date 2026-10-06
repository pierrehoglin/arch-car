"""
Where the car is, for screens to draw.

One reading that always says something, with a word for how much to
trust it:

    gps     a live fix
    last    no fix now; where the car was when it last had one --
            a few seconds ago in a tunnel, or before the power went
            off when the GPS is still finding its satellites
    pin     location.latitude and location.longitude are set, and
            the GPS is ignored
    none    nothing at all: no fix, and none ever remembered

gps.py reads the modem; places.py knows the pin and the remembered
position. This puts them in the order a map wants them, so a screen
does not repeat that logic -- and gets them as one payload it can draw
without asking anything else.
"""

import time

from carlib.core import settings
from carlib.location import places

# The last live fix this process saw. Newer than location.last, which
# is written at most once a minute, so losing the signal in a tunnel
# leaves the car where it went in rather than a minute back.
_latest: dict | None = None


def _round(value: float | None, places_: int) -> float | None:
    return None if value is None else round(value, places_)


def _pinned() -> dict | None:
    lat = settings.get('location.latitude')
    lon = settings.get('location.longitude')
    if lat is None or lon is None:
        return None
    try:
        return {
            'source': 'pin',
            'latitude': float(lat),
            'longitude': float(lon),
            'altitude': settings.get_float('location.altitude', 0.0) or None,
            'speed_kmh': None,
            'heading': None,
            'hdop': None,
            'satellites': 0,
            'at': None,
        }
    except (TypeError, ValueError):
        return None


def _from_fix(fix) -> dict:
    return {
        'source': 'gps',
        'latitude': round(fix.latitude, 6),
        'longitude': round(fix.longitude, 6),
        'altitude': _round(fix.altitude, 1),
        'speed_kmh': _round(fix.speed_kmh, 1),
        'heading': _round(fix.heading, 0),
        'hdop': fix.hdop,
        'satellites': fix.satellites_used,
        'at': round(time.time(), 1),
    }


def _last() -> dict:
    """Where the car last had a fix, said as such."""
    if _latest is not None:
        # Stopped, not moving at the last speed: a marker that kept
        # its arrow and speed would claim the car is still driving.
        return {**_latest, 'source': 'last', 'speed_kmh': None}

    remembered = places.last_known()
    if remembered is None:
        return {'source': 'none'}

    place, at = remembered
    return {
        'source': 'last',
        'latitude': place.latitude,
        'longitude': place.longitude,
        'altitude': place.altitude,
        'speed_kmh': None,
        'heading': None,
        'hdop': None,
        'satellites': 0,
        'at': at,
    }


async def read() -> dict:
    """The best position there is, and what it is based on."""
    global _latest

    pinned = _pinned()
    if pinned is not None:
        return pinned

    try:
        from carlib.location import gps
        fix = await gps.get()
    except Exception:
        fix = None      # no modem, or ModemManager restarting

    if (fix is not None and fix.has_fix
            and fix.latitude is not None and fix.longitude is not None):
        _latest = _from_fix(fix)
        return _latest

    return _last()


def same(a: dict | None, b: dict | None) -> bool:
    """
    Whether two readings would draw the same.

    The time is left out: it moves every read, and comparing it would
    publish a parked car once a second for nothing.
    """
    if a is None or b is None:
        return a is b
    strip = lambda r: {k: v for k, v in r.items() if k != 'at'}
    return strip(a) == strip(b)
