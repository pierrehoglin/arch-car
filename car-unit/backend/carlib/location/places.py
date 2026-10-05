"""
Named locations.

Somewhere to keep "home" and "work" so anything can use them, not just
the weather. A future navigation feature, a geofence, or a UI shortcut
all want the same list.

Lives beside gps.py because it answers the same question: gps says
where we are, this says where somewhere is.

The name "here" is reserved for the GPS position, so callers can take
a place name and treat the current location as one more entry rather
than special-casing None everywhere.
"""

import math
import time
from dataclasses import dataclass, asdict

from carlib.core import settings, state
from carlib.core.errors import NotAvailableError, NotFoundError

SETTING = 'places'
STATE = 'places'

# Reserved: wherever we are now. Kept up to date by the geocoder as
# the car moves, so code can ask for the "current" place instead of
# reading the GPS and geocoding it by hand.
CURRENT = 'current'

# Older name for the same thing, still accepted.
HERE = 'here'

RESERVED = (CURRENT, HERE)

# Where the car last had a fix, kept in the settings file so it
# survives a power cut. Not the same thing as location.latitude and
# location.longitude: those pin the position and make the GPS ignored,
# while this is only used until the GPS has a fix again.
LAST = 'location.last'

# How often the last position is written, at most. Once a minute while
# moving is enough to come back within a minute's driving of where the
# car stopped, and keeps writes to the SD card to about sixty an hour.
REMEMBER_SECONDS = 60.0

# And only if it has moved this far, so a parked car writes nothing.
# Small enough that pulling into a space after the last write still
# moves the remembered spot to where the car actually stopped.
REMEMBER_METRES = 25.0


@dataclass
class Place:
    name: str
    latitude: float
    longitude: float
    altitude: float | None = None

    # Street address, when one is known. Filled in by the geocoder --
    # for saved places when they are created, and continuously for
    # "current".
    address: str = ''

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def label(self) -> str:
        return f'{self.name}  {self.latitude:.4f}, {self.longitude:.4f}'

    @property
    def description(self) -> str:
        """Address if known, coordinates otherwise."""
        return (self.address
                or f'{self.latitude:.4f}, {self.longitude:.4f}')

    @property
    def is_current(self) -> bool:
        return self.name.lower() in RESERVED


def saved() -> list[Place]:
    """
    Every saved place, by name.

    Not called all() -- that shadows the builtin inside this module,
    which works but is a trap for anything added later.
    """
    result = []
    for entry in settings.get_list(SETTING, []):
        if not isinstance(entry, dict):
            continue
        try:
            result.append(Place(
                name=str(entry['name']),
                latitude=float(entry['latitude']),
                longitude=float(entry['longitude']),
                altitude=(float(entry['altitude'])
                          if entry.get('altitude') is not None else None),
                address=str(entry.get('address', '')),
            ))
        except (KeyError, TypeError, ValueError):
            continue

    result.sort(key=lambda p: p.name.lower())
    return result


def find(name: str) -> Place | None:
    """Look up by name, exact first, then substring."""
    lowered = str(name).strip().lower()
    if not lowered:
        return None

    for place in saved():
        if place.name.lower() == lowered:
            return place
    for place in saved():
        if lowered in place.name.lower():
            return place
    return None


async def save(name: str, latitude: float, longitude: float,
               altitude: float | None = None,
               address: str = '',
               lookup: bool = True) -> list[Place]:
    """
    Add or move a place. The name is the key.

    Looks up the address unless one is given, so a saved place reads
    as somewhere rather than a pair of numbers. That is a geocoding
    request, but a user-triggered one -- which is what the Nominatim
    policy permits. Pass lookup=False to skip it.
    """
    clean = str(name).strip()
    if not clean:
        raise NotAvailableError('a place needs a name')
    if clean.lower() in RESERVED:
        raise NotAvailableError(
            f'"{clean}" is reserved for the current position')

    if not address and lookup:
        try:
            from carlib.location import geocoding
            found = await geocoding.reverse(latitude, longitude)
            address = found.short
        except Exception:
            address = ''        # a name and coordinates are enough

    kept = [p for p in saved() if p.name.lower() != clean.lower()]
    kept.append(Place(name=clean, latitude=latitude,
                      longitude=longitude, altitude=altitude,
                      address=address))
    kept.sort(key=lambda p: p.name.lower())
    settings.set(SETTING, [p.to_dict() for p in kept])
    return kept


def remove(name: str) -> list[Place]:
    existing = saved()
    kept = [p for p in existing
            if p.name.lower() != str(name).strip().lower()]
    if len(kept) == len(existing):
        raise NotFoundError('place', name, [p.name for p in existing])
    settings.set(SETTING, [p.to_dict() for p in kept])
    return kept


def set_current(latitude: float, longitude: float,
                altitude: float | None = None,
                address: str = '') -> None:
    """
    Record where we are.

    Called by the geocoder as the car moves. Runtime state, not
    settings: the current position is not something to persist across
    an ignition cycle.
    """
    data = state.read(STATE)
    data['current'] = {
        'latitude': latitude,
        'longitude': longitude,
        'altitude': altitude,
        'address': address or data.get('current', {}).get('address', ''),
    }
    state.write(STATE, data)


def current() -> Place | None:
    """
    Where we are, as a Place, without touching the GPS.

    This is the one to reach for: the geocoder keeps it current, so
    callers get a position and an address together rather than
    reading a fix and looking it up themselves.

    None before the first fix.
    """
    data = state.read(STATE).get('current')
    if not isinstance(data, dict):
        return None
    try:
        return Place(
            name=CURRENT,
            latitude=float(data['latitude']),
            longitude=float(data['longitude']),
            altitude=(float(data['altitude'])
                      if data.get('altitude') is not None else None),
            address=str(data.get('address', '')),
        )
    except (KeyError, TypeError, ValueError):
        return None


async def here() -> Place:
    """
    Where we are now, asking the GPS if need be.

    Prefers the position the geocoder already recorded, so the common
    case costs nothing. Falls back to a fresh fix, and when the GPS has
    none yet -- the first minutes after the ignition -- to where the
    car last was. A parked car has not moved, so that is usually right,
    and the weather for where the car was is better than none.
    """
    known = current()
    if known is not None:
        return known

    try:
        return await fix()
    except NotAvailableError:
        last = last_known()
        if last is None:
            raise
        return last[0]


# --- Last known position ----------------------------------------------------

def _metres(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance. Here rather than borrowed from geocoding,
    which imports this module."""
    r = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = (math.sin(dp / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2)
    return 2 * r * math.asin(math.sqrt(a))


def last_known() -> tuple[Place, float] | None:
    """Where the car last had a fix, and when (Unix seconds)."""
    data = settings.get_dict(LAST, {})
    try:
        place = Place(
            name=CURRENT,
            latitude=float(data['latitude']),
            longitude=float(data['longitude']),
            altitude=(float(data['altitude'])
                      if data.get('altitude') is not None else None),
            address=str(data.get('address', '')),
        )
        return place, float(data.get('at', 0.0))
    except (KeyError, TypeError, ValueError):
        return None


def remember(latitude: float, longitude: float,
             altitude: float | None = None,
             address: str = '') -> bool:
    """
    Keep this fix as the last known position, if it is worth a write.

    Throttled -- see REMEMBER_SECONDS and REMEMBER_METRES -- because
    every write is the whole settings file to the SD card. Returns
    whether it wrote.
    """
    previous = last_known()
    now = time.time()

    if previous is not None:
        place, at = previous
        if now - at < REMEMBER_SECONDS:
            return False
        if _metres(place.latitude, place.longitude,
                   latitude, longitude) < REMEMBER_METRES:
            return False

    settings.set(LAST, {
        'latitude': round(latitude, 6),
        'longitude': round(longitude, 6),
        'altitude': altitude,
        'address': address,
        'at': round(now, 1),
    })
    return True


async def fix() -> Place:
    """
    A fresh position from the GPS.

    Unless `location.latitude` and `location.longitude` pin it, which
    is mainly useful on a bench with no sky view.
    """
    lat = settings.get('location.latitude')
    lon = settings.get('location.longitude')

    if lat is not None and lon is not None:
        try:
            return Place(name=CURRENT, latitude=float(lat),
                         longitude=float(lon),
                         altitude=settings.get_float(
                             'location.altitude', 0.0) or None)
        except (TypeError, ValueError):
            pass        # fall through to GPS rather than failing

    try:
        from carlib.location import gps
        reading = await gps.get()
    except Exception as exc:
        raise NotAvailableError(
            f'no location available: {exc}',
            hint='wait for a GPS fix, or set location.latitude and '
                 'location.longitude') from None

    if (not reading.has_fix or reading.latitude is None
            or reading.longitude is None):
        raise NotAvailableError(
            'no GPS fix yet',
            hint='cold starts take minutes; or set location.latitude '
                 'and location.longitude to pin a position')

    return Place(name=CURRENT, latitude=reading.latitude,
                 longitude=reading.longitude,
                 altitude=reading.altitude)


async def resolve(name: str | None = None) -> Place:
    """
    Turn a place name into coordinates.

    None or "here" means the GPS position, so callers can accept an
    optional name and not special-case the current location.
    """
    if name is None or str(name).strip().lower() in RESERVED:
        return await here()

    found = find(name)
    if found is None:
        raise NotFoundError('place', name,
                            [CURRENT] + [p.name for p in saved()])
    return found
