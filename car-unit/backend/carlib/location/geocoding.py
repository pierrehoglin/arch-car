"""
Geocoding, via Nominatim (OpenStreetMap).

Forward: an address or place name to coordinates, for finding a
navigation target or checking the weather somewhere else. Reverse:
coordinates to an address, so the unit can say what street it is on.

OpenWeather's geocoding was the alternative, but it resolves only to
city level -- no good for either job here.

USAGE POLICY

    https://operations.osmfoundation.org/policies/nominatim/

Nominatim runs on donated servers with very limited capacity, and the
policy is binding. In summary:

  * No heavy use -- an absolute maximum of 1 request per second.
  * A User-Agent or Referer identifying the application is required.
    Stock user agents set by HTTP libraries will not do.
  * Attribution must be clearly displayed, as suitable for the medium.
  * Data is under ODbL, which requires share-alike.
  * Use directly triggered by an end user is fine, provided the number
    of users is moderate.
  * Anything run at regular intervals is restricted to 4 requests per
    minute, and results must be cached. Clients repeatedly sending the
    same query may be classified as faulty and blocked.

This module enforces those: a minimum gap between requests, a cache
keyed to roughly a city block, and -- for the automatic reverse
lookups -- a distance gate so a parked car issues no requests at all.

Set `contact` so the User-Agent identifies you:

    settings set contact you@example.com

Searches are restricted to one country -- Sweden by default -- since
a car asks about places it can drive to:

    settings set geocoding.country se
"""

import math
import time
import asyncio
from collections import deque
from datetime import datetime, timezone
from dataclasses import dataclass, asdict

from carlib.core import settings, state
from carlib.core.errors import NotAvailableError, NotFoundError

SEARCH_URL = 'https://nominatim.openstreetmap.org/search'
REVERSE_URL = 'https://nominatim.openstreetmap.org/reverse'

# Photon, for type-ahead. Nominatim forbids autocomplete outright --
# it is listed among the uses that get you banned -- because the
# query pattern is expensive against its database. Photon indexes the
# same OpenStreetMap data in OpenSearch specifically for
# search-as-you-type, which is why the OSM community points at it for
# exactly this.
#
#     https://github.com/komoot/photon
#
# The demo server is free and unauthenticated, and its terms are that
# requests stay within a reasonable limit; extensive usage will be
# throttled or banned outright. There is no published number, and
# they offer no availability guarantee -- for anything heavier they
# ask you to run your own instance, which is why the URL is a
# setting.
DEFAULT_PHOTON_URL = 'https://photon.komoot.io'

# Matching what other Photon clients default to for the public server.
PHOTON_MIN_INTERVAL = 1.0

# Below this a query matches half the country and the results are
# useless, so it is not worth a request.
MIN_SUGGEST_CHARS = 3

# Bias suggestions towards where we are. On by default: "Kungsgatan"
# exists in most Swedish towns and the one you want is the one you
# are near. Off is right when searching somewhere you are not -- a
# destination on the other side of the country would otherwise rank
# below every local street of a similar name.
DEFAULT_BIAS = True

ATTRIBUTION = 'Data \u00a9 OpenStreetMap contributors (ODbL)'

STATE = 'geocoding'

REQUEST_TIMEOUT = 15.0

# A tenth of a second of headroom over the 1 req/s hard limit. This is
# a floor for every request, manual or automatic.
MIN_INTERVAL = 1.1

# Automatic reverse lookups are "run at regular intervals" as the
# policy puts it, so they are held to the stricter 4 per minute.
#
# Enforced as a budget that declines, not a delay that waits. Waiting
# would stall the caller and, worse, would still let a lowered
# distance threshold queue up more requests than the policy allows --
# they would just arrive late. Declining keeps the ceiling real
# whatever the threshold is set to.
AUTO_MAX_PER_MINUTE = 4
AUTO_WINDOW = 60.0

# How far the car must move before its address is looked up again.
# At motorway speed a kilometre takes about 40 seconds. Lower it for
# more detail in town -- the budget above stops that turning into
# more requests than the policy permits.
DEFAULT_MOVE_METRES = 1000.0

# A short move still counts once the address has gone stale. Turning
# off a main road changes where you are without covering much ground,
# and this catches that without polling.
DEFAULT_STALE_SECONDS = 120.0
DEFAULT_MIN_MOVE_METRES = 50.0

# Cached addresses, keyed to about a city block. Finer would mean a
# fresh request every few houses.
CACHE_PRECISION = 3
CACHE_LIMIT = 200

# Searches are limited to this country by default. A car unit asks
# about places it can drive to, and an unrestricted search puts
# Stockholm, Wisconsin above Stockholm, Sweden. Clear the setting to
# search everywhere.
DEFAULT_COUNTRY = 'se'

_last_request = 0.0
_lock = asyncio.Lock()

_last_photon = 0.0
_photon_lock = asyncio.Lock()

# Timestamps of recent automatic requests, for the per-minute budget.
_auto_requests: deque = deque()


@dataclass
class Address:
    """
    A geocoded location.

    Nominatim returns a deep address object whose keys vary by
    country and by what OSM happens to know, so most fields are
    frequently empty.
    """

    display_name: str = ''
    latitude: float = 0.0
    longitude: float = 0.0

    house_number: str = ''
    road: str = ''
    neighbourhood: str = ''
    suburb: str = ''
    postcode: str = ''
    city: str = ''
    municipality: str = ''
    county: str = ''
    state: str = ''
    country: str = ''
    country_code: str = ''

    # The feature's own name, when it has one -- a park, a shop, a
    # station. Nominatim files these under a key named after the
    # feature type rather than a consistent "name" field.
    name: str = ''

    category: str = ''          # OSM class, e.g. "highway", "place"
    kind: str = ''              # OSM type, e.g. "residential"
    osm_id: str = ''

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def street(self) -> str:
        """Street with house number, when both are known."""
        if self.road and self.house_number:
            return f'{self.road} {self.house_number}'
        return self.road

    @property
    def town(self) -> str:
        """The most useful settlement name available."""
        return (self.city or self.municipality or self.suburb
                or self.county)

    @property
    def short(self) -> str:
        """
        A one-line description, as a car dashboard would show it.

        Falls back through progressively coarser detail rather than
        going blank: a motorway between towns has no house number, and
        often no road name either.
        """
        parts = [p for p in (self.name or self.street, self.town)
                 if p]
        if parts:
            return ', '.join(parts)
        if self.display_name:
            # Nominatim's display_name runs to the country; the first
            # couple of fields are the useful part.
            return ', '.join(self.display_name.split(', ')[:2])
        return f'{self.latitude:.4f}, {self.longitude:.4f}'

    @property
    def label(self) -> str:
        return self.display_name or self.short


def distance_metres(lat1: float, lon1: float,
                    lat2: float, lon2: float) -> float:
    """
    Great-circle distance between two points.

    Haversine. Accurate enough to decide whether we have moved far
    enough to re-query, which is all it is used for.
    """
    radius = 6_371_000.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)

    a = (math.sin(dphi / 2) ** 2
         + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2)
    return 2 * radius * math.asin(min(1.0, math.sqrt(a)))


def user_agent() -> str:
    """
    Identification for Nominatim.

    The policy requires something that identifies the application;
    a stock library user agent is explicitly not acceptable.
    """
    contact = settings.get_str('contact', '')
    if contact:
        return f'carlib-car-unit/0.1 ({contact})'
    return 'carlib-car-unit/0.1 (+https://github.com/unknown/car-unit)'


def parse_address(payload: dict) -> Address:
    """Turn one Nominatim result into an Address."""
    parts = payload.get('address') or {}

    def first(*keys: str) -> str:
        for key in keys:
            value = parts.get(key)
            if value:
                return str(value)
        return ''

    try:
        latitude = float(payload.get('lat', 0.0))
        longitude = float(payload.get('lon', 0.0))
    except (TypeError, ValueError):
        latitude = longitude = 0.0

    # A named feature is filed under its own type -- "park",
    # "amenity", "shop" -- so there is no single key to read. Falling
    # back to the first component of display_name catches the rest.
    name = payload.get('name') or ''
    if not name:
        kind = str(payload.get('type', ''))
        name = parts.get(kind) or ''
    if not name and payload.get('class') in ('leisure', 'amenity',
                                             'tourism', 'shop',
                                             'railway', 'aeroway'):
        head = str(payload.get('display_name', '')).split(', ')[0]
        # Only if it is not simply the house number.
        if head and not head.isdigit():
            name = head

    return Address(
        display_name=str(payload.get('display_name', '')),
        name=str(name),
        latitude=latitude,
        longitude=longitude,
        house_number=first('house_number'),
        road=first('road', 'pedestrian', 'footway', 'path'),
        neighbourhood=first('neighbourhood', 'quarter'),
        suburb=first('suburb', 'city_district', 'district'),
        postcode=first('postcode'),
        # Nominatim uses whichever of these OSM has; a Swedish
        # tätort is usually 'town' or 'village', not 'city'.
        city=first('city', 'town', 'village', 'hamlet'),
        municipality=first('municipality'),
        county=first('county'),
        state=first('state', 'region'),
        country=first('country'),
        country_code=first('country_code').upper(),
        category=str(payload.get('class', '')),
        kind=str(payload.get('type', '')),
        osm_id=str(payload.get('osm_id', '')),
    )


# --- Cache -----------------------------------------------------------------

def _cache_key(latitude: float, longitude: float) -> str:
    return (f'{round(latitude, CACHE_PRECISION)}:'
            f'{round(longitude, CACHE_PRECISION)}')


def _cached(key: str) -> Address | None:
    entry = (state.read(STATE).get('addresses') or {}).get(key)
    if not isinstance(entry, dict):
        return None
    try:
        return Address(**{k: v for k, v in entry.items()
                          if k in Address.__dataclass_fields__})
    except TypeError:
        return None


def _remember(key: str, address: Address) -> None:
    data = state.read(STATE)
    addresses = data.get('addresses')
    if not isinstance(addresses, dict):
        addresses = {}

    addresses[key] = address.to_dict()

    # Bounded, oldest dropped. Python dicts keep insertion order, so
    # this is the least recently added rather than least used -- good
    # enough for a cache whose job is stopping repeat queries.
    while len(addresses) > CACHE_LIMIT:
        addresses.pop(next(iter(addresses)))

    data['addresses'] = addresses
    state.write(STATE, data)


# --- Requests --------------------------------------------------------------

async def _get(url: str, params: dict,
               interval: float = MIN_INTERVAL,
               photon: bool = False) -> object:
    """
    One request, no faster than the service allows.

    The gap is enforced under a lock so concurrent callers queue
    rather than all firing at once. Nominatim and Photon are paced
    separately -- they are different services with different limits,
    and one should not be held up by the other.
    """
    global _last_request, _last_photon

    try:
        import httpx
    except ImportError as exc:
        raise NotAvailableError('httpx is not installed',
                                hint='uv sync') from exc

    lock = _photon_lock if photon else _lock

    async with lock:
        loop = asyncio.get_running_loop()
        last = _last_photon if photon else _last_request
        wait = interval - (loop.time() - last)
        if wait > 0:
            await asyncio.sleep(wait)

        headers = {'User-Agent': user_agent(),
                   'Accept': 'application/json'}

        try:
            async with httpx.AsyncClient(
                    timeout=REQUEST_TIMEOUT,
                    follow_redirects=True) as client:
                response = await client.get(url, params=params,
                                            headers=headers)
        except Exception as exc:
            raise NotAvailableError(
                f'cannot reach {"Photon" if photon else "Nominatim"}: '
                f'{exc}',
                hint='check the network connection') from exc
        finally:
            if photon:
                _last_photon = loop.time()
            else:
                _last_request = loop.time()

    service = 'Photon' if photon else 'Nominatim'

    if response.status_code == 403:
        raise NotAvailableError(
            f'{service} refused the request (403)',
            hint='the User-Agent must identify this application, and '
                 'the rate limit is 1 request per second. See '
                 'https://operations.osmfoundation.org/policies/'
                 'nominatim/')
    if response.status_code == 429:
        raise NotAvailableError(
            f'{service} rate limited this client (429)',
            hint='requests are being made too often; see '
                 'https://operations.osmfoundation.org/policies/'
                 'nominatim/')
    if response.status_code >= 400:
        raise NotAvailableError(
            f'{service} request failed ({response.status_code})')

    try:
        return response.json()
    except ValueError as exc:
        raise NotAvailableError(
            f'{service} response was not JSON') from exc


def default_country() -> str:
    """
    Country to restrict searches to, as an ISO 3166-1 alpha-2 code.

    Set `geocoding.country` to change it, or to an empty string to
    search worldwide.
    """
    return settings.get_str('geocoding.country', DEFAULT_COUNTRY)


async def search(query: str, limit: int = 5,
                 country: str | None = None) -> list[Address]:
    """
    Find places matching a name or address.

    User-triggered, which the policy explicitly permits: looking up a
    navigation target or somewhere to check the weather.

    Restricted to one country by default, because an unrestricted
    search ranks by importance rather than by distance -- "Stockholm"
    can return Wisconsin. Pass country='' to search everywhere.
    """
    text = str(query).strip()
    if not text:
        raise NotFoundError('place', query, [])

    if country is None:
        country = default_country()

    params = {
        'q': text,
        'format': 'jsonv2',
        'limit': max(1, min(int(limit), 20)),
        'addressdetails': 1,
    }
    if country:
        params['countrycodes'] = country.strip().lower()

    payload = await _get(SEARCH_URL, params)
    if not isinstance(payload, list):
        return []

    return [parse_address(item) for item in payload]


# --- Autocomplete ----------------------------------------------------------

def photon_url() -> str:
    return settings.get_str('geocoding.photon_url',
                            DEFAULT_PHOTON_URL).rstrip('/')


def default_bias() -> bool:
    """Whether suggestions are biased towards the current position."""
    return settings.get_bool('geocoding.bias', DEFAULT_BIAS)


def parse_photon(feature: dict) -> Address:
    """
    One Photon GeoJSON feature.

    A flatter shape than Nominatim: address components sit directly in
    properties rather than nested, and coordinates are GeoJSON order,
    longitude first.
    """
    props = feature.get('properties') or {}
    coords = (feature.get('geometry') or {}).get('coordinates') or []

    try:
        longitude = float(coords[0])
        latitude = float(coords[1])
    except (IndexError, TypeError, ValueError):
        latitude = longitude = 0.0

    def text(key: str) -> str:
        value = props.get(key)
        return str(value) if value else ''

    address = Address(
        latitude=latitude,
        longitude=longitude,
        name=text('name'),
        house_number=text('housenumber'),
        road=text('street'),
        suburb=text('district'),
        postcode=text('postcode'),
        city=text('city'),
        county=text('county'),
        state=text('state'),
        country=text('country'),
        country_code=text('countrycode').upper(),
        category=text('osm_key'),
        kind=text('osm_value'),
        osm_id=text('osm_id'),
    )

    # Photon has no display_name, so build one. Without it a result
    # is hard to tell apart from others of the same name.
    parts = [p for p in (address.name or address.street,
                         address.house_number if address.name else '',
                         address.postcode, address.city or address.county,
                         address.state, address.country) if p]
    address.display_name = ', '.join(dict.fromkeys(parts))

    return address


async def suggest(query: str, limit: int = 5,
                  latitude: float | None = None,
                  longitude: float | None = None,
                  country: str | None = None,
                  bias: bool | None = None) -> list[Address]:
    """
    Type-ahead suggestions for a partial query.

    Biased towards a position by default, which matters in a car:
    "Kungsgatan" exists in most Swedish towns, and the one you want
    is usually the one you are near. The position comes from the
    argument, or from where we are.

    Pass bias=False to search without it -- right when looking for
    somewhere you are not, since a distant destination would
    otherwise rank below every nearby street of a similar name.
    bias=None follows the `geocoding.bias` setting.

    Explicit coordinates override the setting -- passing a position
    is itself a request to bias towards it -- but bias=False beats
    both, since asking for no bias and getting one would be the wrong
    way round.

    Short queries return nothing rather than making a request -- two
    characters match half the country and would waste a call on
    results nobody wants.

    Photon has no country parameter, so the filter is applied to the
    results. Coarser than Nominatim's, but it costs no extra request.
    """
    text = str(query).strip()
    if len(text) < MIN_SUGGEST_CHARS:
        return []

    if country is None:
        country = default_country()

    explicit = latitude is not None and longitude is not None

    # Three inputs, in order of how deliberate they are:
    #
    #   bias=False        an explicit no, and it wins outright
    #   coordinates       passing a position is asking to bias to it
    #   the setting       what to do when neither was said
    #
    if bias is False:
        latitude = longitude = None
    elif not explicit:
        if bias or (bias is None and default_bias()):
            position = current_position()
            if position is not None:
                latitude, longitude = position
        else:
            latitude = longitude = None

    params: dict = {
        'q': text,
        # Ask for extra, since filtering by country happens after.
        'limit': max(1, min(int(limit) * 3, 50)),
    }
    if latitude is not None and longitude is not None:
        params['lat'] = round(latitude, 4)
        params['lon'] = round(longitude, 4)

    payload = await _get(f'{photon_url()}/api', params,
                         interval=PHOTON_MIN_INTERVAL,
                         photon=True)

    if not isinstance(payload, dict):
        return []

    results = [parse_photon(f) for f in payload.get('features') or []]

    if country:
        wanted = country.strip().upper()
        results = [r for r in results
                   if not r.country_code or r.country_code == wanted]

    return results[:limit]


async def reverse(latitude: float, longitude: float,
                  use_cache: bool = True) -> Address:
    """
    The address at a point.

    Cached to roughly a city block, because the policy requires
    caching and because repeatedly asking the same question is what
    gets a client blocked.
    """
    key = _cache_key(latitude, longitude)

    if use_cache:
        hit = _cached(key)
        if hit is not None:
            return hit

    payload = await _get(REVERSE_URL, {
        'lat': round(latitude, 6),
        'lon': round(longitude, 6),
        'format': 'jsonv2',
        'addressdetails': 1,
        # 18 is building level; anything finer is not useful in a car.
        'zoom': 18,
    })

    if not isinstance(payload, dict) or payload.get('error'):
        message = ''
        if isinstance(payload, dict):
            message = str(payload.get('error', ''))
        raise NotFoundError('address', f'{latitude:.4f},{longitude:.4f}',
                            [message] if message else [])

    address = parse_address(payload)
    _remember(key, address)
    return address


# --- Current position ------------------------------------------------------

def move_threshold() -> float:
    return settings.get_float('geocoding.move_metres',
                              DEFAULT_MOVE_METRES)


def stale_seconds() -> float:
    return settings.get_float('geocoding.stale_seconds',
                              DEFAULT_STALE_SECONDS)


def min_move_metres() -> float:
    return settings.get_float('geocoding.min_move_metres',
                              DEFAULT_MIN_MOVE_METRES)


def auto_budget() -> int:
    """
    Automatic requests still allowed in the current minute.

    A sliding window rather than a fixed interval, because the policy
    limit is per minute: four requests in quick succession followed by
    a quiet minute is within it, and a rigid gap would forbid that
    while permitting nothing better.
    """
    now = time.monotonic()
    while _auto_requests and now - _auto_requests[0] >= AUTO_WINDOW:
        _auto_requests.popleft()
    return max(0, AUTO_MAX_PER_MINUTE - len(_auto_requests))


def _spend_auto() -> None:
    _auto_requests.append(time.monotonic())


def current() -> Address | None:
    """The last address looked up for our own position."""
    data = state.read(STATE).get('current')
    if not isinstance(data, dict):
        return None
    try:
        return Address(**{k: v for k, v in data.items()
                          if k in Address.__dataclass_fields__})
    except TypeError:
        return None


def current_position() -> tuple[float, float] | None:
    """Where the current address was looked up."""
    data = state.read(STATE)
    lat, lon = data.get('current_lat'), data.get('current_lon')
    if lat is None or lon is None:
        return None
    try:
        return float(lat), float(lon)
    except (TypeError, ValueError):
        return None


def current_age() -> float | None:
    """Seconds since the current address was looked up."""
    raw = state.read(STATE).get('current_at')
    if not raw:
        return None
    try:
        when = datetime.fromisoformat(str(raw))
    except ValueError:
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - when).total_seconds()


def _store_current(address: Address, latitude: float,
                   longitude: float) -> None:
    data = state.read(STATE)
    data['current'] = address.to_dict()
    data['current_at'] = datetime.now(timezone.utc).isoformat()
    data['current_lat'] = latitude
    data['current_lon'] = longitude
    state.write(STATE, data)


def should_update(latitude: float, longitude: float) -> bool:
    """
    Whether this position warrants a fresh lookup.

    Two ways to qualify: a long move, or a short one after the
    address has gone stale. The second matters because turning off a
    main road changes where you are without covering much ground --
    but it still requires actual movement, so a parked car never
    qualifies however long it sits there.
    """
    position = current_position()
    if position is None:
        return True

    moved = distance_metres(position[0], position[1],
                            latitude, longitude)

    if moved >= move_threshold():
        return True

    age = current_age()
    return (moved >= min_move_metres()
            and age is not None and age >= stale_seconds())


# Kept as the old name for callers that only want the distance test.
def moved_enough(latitude: float, longitude: float,
                 threshold: float | None = None) -> bool:
    position = current_position()
    if position is None:
        return True
    if threshold is None:
        threshold = move_threshold()
    return distance_metres(position[0], position[1],
                           latitude, longitude) >= threshold


async def update_current(latitude: float, longitude: float,
                         force: bool = False) -> Address | None:
    """
    Refresh our own address if the position warrants it.

    Returns the address when it was looked up again, None when either
    gate declined -- so a caller can tell a change from a no-op.

    The budget is checked before the distance gate, and declining
    costs nothing: skipping a lookup means the address stays a little
    stale, which is a far better failure than being blocked by the
    service.
    """
    if not force:
        if not should_update(latitude, longitude):
            return None
        if auto_budget() <= 0:
            return None

    if not force:
        _spend_auto()

    address = await reverse(latitude, longitude)
    _store_current(address, latitude, longitude)

    # Keep the "current" place in step, so anything reading places
    # sees the same position and address without asking the GPS.
    try:
        from carlib.location import places
        places.set_current(latitude, longitude, address=address.short)
    except Exception:
        pass        # places is a convenience here, not a dependency

    return address


async def watch(interval: float = 30.0):
    """
    Keep our own address current as the car moves.

    Yields an Address only when it actually changes, so a caller can
    log or display without filtering.

    The GPS is polled often; Nominatim is not. Every poll checks the
    distance gate, which costs nothing, and only a real move triggers
    a request. Parked, this makes no network calls at all -- which is
    what keeps automatic use inside the usage policy.

    Should run in one process only. Two copies would each hold their
    own rate limiter and between them could exceed the limit.
    """
    from carlib.location import gps

    while True:
        try:
            fix = await gps.get()
        except Exception:
            await asyncio.sleep(interval)
            continue

        if (fix.has_fix and fix.latitude is not None
                and fix.longitude is not None):
            try:
                address = await update_current(fix.latitude,
                                               fix.longitude)
            except (NotAvailableError, NotFoundError):
                address = None      # no signal, or nothing mapped here

            if address is not None:
                yield address

        await asyncio.sleep(interval)
