"""
The weather service.

Handles the parts every provider needs but none should implement: how
long to keep an answer, and which provider to ask. Locations come from
carlib.location.places, so "home" means the same thing here as
anywhere else.

Caching is not optional politeness. MET Norway's terms require
respecting the Expires header, and they block clients that poll
regardless -- so the cache is what keeps the service usable.
"""

from datetime import datetime, timezone

from carlib.core import settings, state
from carlib.core.errors import NotAvailableError
from carlib.weather import base
from carlib.location import places
from carlib.weather.types import Conditions, Forecast

# Registering the built-in providers. Adding one means importing it
# here; removing one means deleting the import and the module.
from carlib.weather import metno         # noqa: F401
from carlib.weather import openweather   # noqa: F401

STATE = 'weather'

# Fallback when a provider gives no Expires header. MET Norway updates
# roughly hourly, and asking more often than this would be rude to any
# free service.
DEFAULT_TTL_SECONDS = 1800

# Refuse to serve a cached forecast older than this even if the
# network is down. A day-old forecast presented as current is worse
# than admitting we do not know.
MAX_AGE_SECONDS = 6 * 3600

# Cached locations to keep. Enough for the saved places plus a drive,
# without letting a long journey accumulate one entry per kilometre.
MAX_CACHE_ENTRIES = 12


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _cache_key(provider: str, lat: float, lon: float) -> str:
    """
    Coordinates rounded to two decimals -- about a kilometre.

    Finer would mean a fresh request every few hundred metres of
    driving, and the forecast does not change on that scale.
    """
    return f'{provider}:{lat:.2f}:{lon:.2f}'


def _load_cache(key: str) -> Forecast | None:
    """
    A cached forecast, if one exists for this location.

    Entries are keyed by location rather than there being a single
    slot: checking the weather at home while driving must not evict
    the local forecast, which is the whole point of saved places.
    """
    entry = (state.read(STATE).get('entries') or {}).get(key)
    if not isinstance(entry, dict):
        return None

    payload = entry.get('forecast')
    if not isinstance(payload, dict):
        return None

    from carlib.api.serialise import from_dict
    forecast = from_dict(Forecast, payload)

    # from_dict leaves datetimes as strings, so restore them.
    forecast.updated = _parse(payload.get('updated'))
    forecast.expires = _parse(payload.get('expires'))
    if forecast.current is not None:
        forecast.current.time = _parse(
            (payload.get('current') or {}).get('time'))
    for entry, raw in zip(forecast.hourly, payload.get('hourly') or []):
        entry.time = _parse(raw.get('time'))

    return forecast


def _parse(value) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    except ValueError:
        return None


def _save_cache(key: str, forecast: Forecast) -> None:
    data = state.read(STATE)
    entries = data.get('entries')
    if not isinstance(entries, dict):
        entries = {}

    entries[key] = {
        'fetched': _now().isoformat(),
        'forecast': forecast.to_dict(),
    }

    # Bound it. A long drive would otherwise accumulate an entry every
    # kilometre, so keep the most recently fetched few.
    if len(entries) > MAX_CACHE_ENTRIES:
        ordered = sorted(entries.items(),
                         key=lambda kv: kv[1].get('fetched', ''))
        entries = dict(ordered[-MAX_CACHE_ENTRIES:])

    data['entries'] = entries
    state.write(STATE, data)


def _fetched_at(key: str) -> datetime | None:
    entry = (state.read(STATE).get('entries') or {}).get(key) or {}
    return _parse(entry.get('fetched'))


def _expired(forecast: Forecast, key: str) -> bool:
    if forecast.expires is not None:
        return _now() >= forecast.expires

    fetched = _fetched_at(key)
    if fetched is None:
        return True
    return (_now() - fetched).total_seconds() > DEFAULT_TTL_SECONDS


async def forecast(place: str | None = None,
                   latitude: float | None = None,
                   longitude: float | None = None,
                   altitude: float | None = None,
                   provider: str | None = None,
                   refresh: bool = False) -> Forecast:
    """
    A forecast for a saved place, explicit coordinates, or here.

    Each place caches separately, because the cache key is built from
    coordinates -- so checking the forecast at home while driving
    somewhere else does not evict the local one.

    Served from cache until the provider says it has expired. On a
    network failure a stale cache is returned rather than nothing --
    an hour-old forecast in a tunnel beats an error -- but only up to
    MAX_AGE_SECONDS.
    """
    if latitude is None or longitude is None:
        resolved = await places.resolve(place)
        latitude = resolved.latitude
        longitude = resolved.longitude
        altitude = resolved.altitude
        name = resolved.name
    else:
        name = place or ''

    service = base.get(provider)
    key = _cache_key(service.name, latitude, longitude)

    cached = _load_cache(key)
    if (cached is not None and not refresh
            and not _expired(cached, key)):
        cached.place = name
        return cached

    try:
        fresh = await service.fetch(latitude, longitude, altitude)
    except NotAvailableError:
        if cached is not None:
            fetched = _fetched_at(key)
            age = ((_now() - fetched).total_seconds()
                   if fetched else MAX_AGE_SECONDS + 1)
            if age <= MAX_AGE_SECONDS:
                return cached
        raise

    fresh.place = name
    _save_cache(key, fresh)
    return fresh


async def current(**kwargs) -> Conditions:
    """Conditions right now."""
    result = await forecast(**kwargs)
    if result.current is None:
        raise NotAvailableError('the forecast contained no data')
    return result.current


def providers() -> list[dict]:
    """Every registered provider, for display."""
    rows = []
    for name in base.available():
        cls = base._providers[name]
        rows.append({
            'name': name,
            'description': cls.description,
            'global': cls.global_coverage,
            'active': name == settings.get_str('weather.provider',
                                               base.DEFAULT_PROVIDER),
        })
    return rows


def clear_cache() -> None:
    state.clear(STATE)
