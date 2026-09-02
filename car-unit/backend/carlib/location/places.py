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
    case costs nothing. Falls back to a fresh fix.
    """
    known = current()
    if known is not None:
        return known

    return await fix()


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
