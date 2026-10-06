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

describe() adds the address, for screens that say where the car is in
words rather than draw it. That changes far less often than the
position, so it travels separately: the 'position' event about once a
second while moving, the 'place' event when the address changes.
"""

import time

from carlib.core import settings
from carlib.location import geocoding, places

# The last reading, whatever its source. What read() last returned, so
# anything wanting the position between reads -- the place tracker --
# takes it from here instead of asking the modem again.
_reading: dict | None = None

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
    global _reading
    _reading = await _read()
    return _reading


async def _read() -> dict:
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


def latest() -> dict | None:
    """What read() last returned, without reading again. None before
    the first read."""
    return _reading


def located(reading: dict | None) -> bool:
    """Whether a reading has coordinates to speak of."""
    return (reading is not None and reading.get('source') != 'none'
            and reading.get('latitude') is not None
            and reading.get('longitude') is not None)


# --- In words ----------------------------------------------------------------

def address_for(reading: dict) -> 'geocoding.Address | None':
    """
    The geocoder's last address, while it still describes this spot.

    "Still" is the geocoder's own move threshold -- the distance at
    which it would look the address up again anyway -- and half as much
    again, for a lookup the per-minute budget has held back. Further
    than that, the address is somewhere the car has left, and no
    address is the more honest answer.
    """
    known = geocoding.current()
    where = geocoding.current_position()
    if known is None or where is None:
        return None
    reach = 1.5 * max(geocoding.move_threshold(), geocoding.NEAR_METRES)
    if geocoding.distance_metres(where[0], where[1], reading['latitude'],
                                 reading['longitude']) > reach:
        return None
    return known


def describe(reading: dict,
             address: 'geocoding.Address | None') -> dict:
    """
    Where the car is, in words: the 'place' event, and what
    /places/current returns.

    `address` is the full line -- street, postcode and town -- and
    `details` the parts, for a screen that lays them out itself. Both
    empty when there is no address for here yet.
    """
    source = reading.get('source')
    return {
        'name': places.CURRENT,
        'source': source,
        'latitude': reading['latitude'],
        'longitude': reading['longitude'],
        'altitude': reading.get('altitude'),
        'address': address.full if address else '',
        'details': address.to_dict() if address else None,
        'last_known': source == 'last',
        'at': reading.get('at') if source == 'last' else None,
    }


def same_place(a: dict | None, b: dict | None) -> bool:
    """
    Whether two descriptions say the same thing.

    The coordinates are left out: they move every second while
    driving, and the place event is for when the words change.
    """
    if a is None or b is None:
        return a is b
    keys = ('address', 'source', 'last_known')
    return all(a.get(k) == b.get(k) for k in keys)


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
