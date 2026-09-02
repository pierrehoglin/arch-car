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

from carlib.core import settings
from carlib.core.errors import NotAvailableError, NotFoundError

SETTING = 'places'

# Reserved: resolves to wherever the GPS says we are.
HERE = 'here'


@dataclass
class Place:
    name: str
    latitude: float
    longitude: float
    altitude: float | None = None

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def label(self) -> str:
        return f'{self.name}  {self.latitude:.4f}, {self.longitude:.4f}'

    @property
    def is_here(self) -> bool:
        return self.name.lower() == HERE


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


def save(name: str, latitude: float, longitude: float,
         altitude: float | None = None) -> list[Place]:
    """Add or move a place. The name is the key."""
    clean = str(name).strip()
    if not clean:
        raise NotAvailableError('a place needs a name')
    if clean.lower() == HERE:
        raise NotAvailableError(
            f'"{HERE}" is reserved for the GPS position')

    kept = [p for p in saved() if p.name.lower() != clean.lower()]
    kept.append(Place(name=clean, latitude=latitude,
                      longitude=longitude, altitude=altitude))
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


async def here() -> Place:
    """
    Where we are now.

    GPS, unless `location.latitude` and `location.longitude` pin it --
    which is mainly useful on a bench with no sky view.
    """
    lat = settings.get('location.latitude')
    lon = settings.get('location.longitude')

    if lat is not None and lon is not None:
        try:
            return Place(name=HERE, latitude=float(lat),
                         longitude=float(lon),
                         altitude=settings.get_float(
                             'location.altitude', 0.0) or None)
        except (TypeError, ValueError):
            pass        # fall through to GPS rather than failing

    try:
        from carlib.location import gps
        fix = await gps.get()
    except Exception as exc:
        raise NotAvailableError(
            f'no location available: {exc}',
            hint='wait for a GPS fix, or set location.latitude and '
                 'location.longitude') from None

    if not fix.has_fix or fix.latitude is None or fix.longitude is None:
        raise NotAvailableError(
            'no GPS fix yet',
            hint='cold starts take minutes; or set location.latitude '
                 'and location.longitude to pin a position')

    return Place(name=HERE, latitude=fix.latitude,
                 longitude=fix.longitude, altitude=fix.altitude)


async def resolve(name: str | None = None) -> Place:
    """
    Turn a place name into coordinates.

    None or "here" means the GPS position, so callers can accept an
    optional name and not special-case the current location.
    """
    if name is None or str(name).strip().lower() == HERE:
        return await here()

    found = find(name)
    if found is None:
        raise NotFoundError('place', name,
                            [HERE] + [p.name for p in saved()])
    return found
