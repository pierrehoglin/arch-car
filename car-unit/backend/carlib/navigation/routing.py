"""
The Valhalla client.

Two calls matter for a car: /route for directions between points, and
/trace_route for map matching, which snaps a GPS trace onto the road
network.

The public FOSSGIS server carries a full planet graph and is free.
Its terms are the same fair-usage policy as the Nominatim and OSRM
demo servers, enforced at one call per second per user, and they ask
that applications identify themselves with an X-Client-Id header.
Both are handled here.

    https://valhalla.openstreetmap.de

For routing that survives a coverage gap -- which is exactly when a
reroute is needed -- run your own:

    settings set navigation.url http://localhost:8002
"""

import json
import asyncio

from carlib.core import settings
from carlib.core.errors import NotAvailableError, NotFoundError
from carlib.navigation.types import Route, parse_route

DEFAULT_URL = 'https://valhalla1.openstreetmap.de'

# Their published limit for the demo server is one call per second per
# user. A local instance has no such limit, so the pacing is dropped
# when the URL is not the public one.
PUBLIC_MIN_INTERVAL = 1.1

# Asked for by the Valhalla project so they can identify traffic on
# the demo server and get in touch if it causes problems.
CLIENT_ID = 'carlib-car-unit'

REQUEST_TIMEOUT = 30.0

# Valhalla costing models. "auto" is a car; the others exist mainly so
# a caller can ask for them without this module needing to change.
COSTINGS = ('auto', 'bicycle', 'pedestrian', 'motorcycle', 'bus',
            'truck', 'taxi')

_last_request = 0.0
_lock = asyncio.Lock()


def base_url() -> str:
    return settings.get_str('navigation.url', DEFAULT_URL).rstrip('/')


def is_public() -> bool:
    """Whether we are pointed at somebody else's server."""
    return 'openstreetmap.de' in base_url()


def default_costing() -> str:
    costing = settings.get_str('navigation.costing', 'auto')
    return costing if costing in COSTINGS else 'auto'


async def _post(path: str, body: dict) -> dict:
    """
    One request, paced when talking to the public server.

    A local instance is not rate limited, and pacing it would make
    rerouting needlessly sluggish at the moment it matters most.
    """
    global _last_request

    try:
        import httpx
    except ImportError as exc:
        raise NotAvailableError('httpx is not installed',
                                hint='uv sync') from exc

    url = f'{base_url()}{path}'
    interval = PUBLIC_MIN_INTERVAL if is_public() else 0.0

    async with _lock:
        loop = asyncio.get_running_loop()
        if interval:
            wait = interval - (loop.time() - _last_request)
            if wait > 0:
                await asyncio.sleep(wait)

        try:
            async with httpx.AsyncClient(
                    timeout=REQUEST_TIMEOUT,
                    follow_redirects=True) as client:
                response = await client.post(
                    url, json=body,
                    headers={'X-Client-Id': CLIENT_ID,
                             'Content-Type': 'application/json'})
        except Exception as exc:
            raise NotAvailableError(
                f'cannot reach the router: {exc}',
                hint=f'{base_url()} -- check the network, or point '
                     f'navigation.url at a local instance') from exc
        finally:
            _last_request = loop.time()

    if response.status_code == 429:
        raise NotAvailableError(
            'the router rate limited this client (429)',
            hint='the public server allows one call per second; run a '
                 'local instance for more')

    if response.status_code >= 400:
        # Valhalla puts a useful explanation in the body -- "no path
        # could be found" reads far better than "400".
        message = ''
        try:
            payload = response.json()
            message = str(payload.get('error') or '')
        except (ValueError, AttributeError):
            message = response.text[:200]

        if response.status_code == 400 and message:
            raise NotFoundError('route', message, [])
        raise NotAvailableError(
            f'router request failed ({response.status_code}): '
            f'{message}'.strip())

    try:
        return response.json()
    except json.JSONDecodeError as exc:
        raise NotAvailableError(
            'the router response was not JSON') from exc


async def route(points: list[tuple[float, float]],
                costing: str | None = None,
                units: str = 'kilometers',
                alternates: int = 0) -> Route:
    """
    A route through a series of points.

    At least two: where we are and where we are going. Anything in
    between becomes a waypoint.
    """
    if len(points) < 2:
        raise NotFoundError('route', 'fewer than two points',
                            ['a start and a destination are needed'])

    body = {
        'locations': [{'lat': round(lat, 6), 'lon': round(lon, 6)}
                      for lat, lon in points],
        'costing': costing or default_costing(),
        'directions_options': {'units': units},
    }
    if alternates:
        body['alternates'] = int(alternates)

    payload = await _post('/route', body)
    result = parse_route(payload)
    result.costing = body['costing']
    return result


async def match(points: list[tuple[float, float]],
                costing: str | None = None,
                units: str = 'kilometers') -> Route:
    """
    Snap a GPS trace onto the road network.

    For cleaning up a recorded track, or for placing a position when
    the raw fix has wandered off the carriageway. Needs several points
    to work from -- a single fix has no direction to match against.
    """
    if len(points) < 2:
        raise NotFoundError('trace', 'fewer than two points',
                            ['map matching needs a sequence of fixes'])

    body = {
        'shape': [{'lat': round(lat, 6), 'lon': round(lon, 6)}
                  for lat, lon in points],
        'costing': costing or default_costing(),
        # map_snap follows the roads; the alternative, edge_walk,
        # assumes the trace already sits on them.
        'shape_match': 'map_snap',
        'directions_options': {'units': units},
    }

    payload = await _post('/trace_route', body)
    return parse_route(payload)


async def status() -> dict:
    """
    Whether the router is reachable, and what it is.

    Useful for telling "no signal" apart from "wrong URL", which
    otherwise look the same from a failed route.
    """
    try:
        import httpx
    except ImportError as exc:
        raise NotAvailableError('httpx is not installed') from exc

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f'{base_url()}/status',
                headers={'X-Client-Id': CLIENT_ID})
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        raise NotAvailableError(
            f'router not reachable: {exc}',
            hint=f'navigation.url is {base_url()}') from exc

    return {
        'url': base_url(),
        'public': is_public(),
        'version': payload.get('version', ''),
        'tileset_last_modified': payload.get('tileset_last_modified'),
    }
