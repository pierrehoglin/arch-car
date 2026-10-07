"""
The speed limit where the car is.

From the router, which has OpenStreetMap's maxspeed tags on every road
it knows. Two ways of asking, depending on whether there is a route:

    navigating    once per route: the route's line is handed back to
                  /trace_attributes, which answers with the limit on
                  every stretch of it. Looked up by how far along the
                  route the car is, with no more requests until the
                  route changes. Kept with the route on disk, so a
                  resumed route has its limits at once.

    no route      the last few fixes are matched onto the road they
                  follow, which gives that road's limit and how far it
                  is to the end of the stretch -- the next junction, or
                  wherever the limit changes. Asked again at the end of
                  the stretch, after a turn, or after MAX_METRES at the
                  most; never sooner than MIN_SECONDS after the last
                  time, and never while crawling, when the trace says
                  nothing about which road this is.

Published as the 'speedlimit' event only when what the screens show
changes:

    {"shown": bool, "limit": int | None, "source": "route" | "road" | None}

"limit" None with "shown" true is a limit not known -- a road without
the tag, nothing heard yet, or too long without a connection -- and is
drawn as an empty sign.
"""

import asyncio
import logging
import time
from collections import deque
from typing import Callable

from carlib.core import settings
from carlib.core.errors import NotAvailableError, NotFoundError
from carlib.navigation import routing
from carlib.navigation.types import distance_metres, encode_polyline

log = logging.getLogger('carlib')

# Never ask about the road more often than this.
MIN_SECONDS = 15.0

# However long the road, check again after this far.
MAX_METRES = 2000.0

# A turn: the heading this far from where it was when last asked.
TURN_DEGREES = 45.0

# Below this, the fixes do not say which road the car is on.
CRAWL_KMH = 10.0

# How long a limit is believed past the end of its stretch, or past
# MAX_METRES, when asking again has failed -- no signal, mostly.
STALE_METRES = 1000.0

# The fixes matched onto a road: enough to tell it from the one beside
# it, few enough to be about this road and not the last one.
TRAIL_POINTS = 8
TRAIL_SPACING = 10.0

# Between attempts to fetch a route's limits after a failure.
ROUTE_RETRY_SECONDS = 30.0


def _limit(value) -> int | None:
    """A posted limit in km/h, or None. Valhalla gives 0 for a road
    without the tag; anything absurd is treated the same."""
    try:
        kmh = int(round(float(value)))
    except (TypeError, ValueError):
        return None
    return kmh if 0 < kmh < 200 else None


def _turned(a: float | None, b: float | None) -> bool:
    if a is None or b is None:
        return False
    return abs((b - a + 180) % 360 - 180) > TURN_DEGREES


async def spans_for(route) -> list[list]:
    """
    The limits along a route: [start, end, km/h or None], in metres
    from its start.

    By length rather than by the router's shape indices: those count
    points of the line it matched, which need not be the points of the
    line sent. The lengths are scaled to the route's own, so a partial
    first or last edge does not shift everything after it.
    """
    shape = route.shape
    if len(shape) < 2:
        return []
    body = {
        'encoded_polyline': encode_polyline(shape),
        # The line came from the router, so it sits on its roads
        # exactly: edge_walk follows it rather than guessing.
        'shape_match': 'edge_walk',
        'costing': route.costing or routing.default_costing(),
        'filters': {
            'attributes': ['edge.speed_limit', 'edge.length'],
            'action': 'include',
        },
    }
    payload = await routing._post('/trace_attributes', body)
    edges = payload.get('edges') or []
    lengths = [max(0.0, float(e.get('length') or 0.0)) * 1000 for e in edges]
    total = sum(lengths)
    if not total:
        return []

    scale = route.distance_metres / total if route.distance_metres else 1.0
    if not 0.8 <= scale <= 1.25:
        scale = 1.0

    spans: list[list] = []
    at = 0.0
    for edge, length in zip(edges, lengths):
        end = at + length * scale
        kmh = _limit(edge.get('speed_limit'))
        # Neighbouring edges with the same limit as one span: the
        # junctions between them change nothing anyone can see.
        if spans and spans[-1][2] == kmh:
            spans[-1][1] = round(end, 1)
        else:
            spans.append([round(at, 1), round(end, 1), kmh])
        at = end
    return spans


async def road_at(trail: list[tuple[float, float]]) -> tuple[int | None, float]:
    """
    The limit on the road the fixes lead along, and how many metres
    of it are left past the last of them.
    """
    body = {
        'shape': [{'lat': round(lat, 6), 'lon': round(lon, 6)}
                  for lat, lon in trail],
        'costing': routing.default_costing(),
        # Fixes wander off the carriageway; map_snap puts them on it.
        'shape_match': 'map_snap',
        'filters': {
            'attributes': ['edge.speed_limit', 'edge.length',
                           'matched.edge_index',
                           'matched.distance_along_edge',
                           'matched.type'],
            'action': 'include',
        },
    }
    payload = await routing._post('/trace_attributes', body)
    edges = payload.get('edges') or []
    matched = [m for m in payload.get('matched_points') or []
               if m.get('type') != 'unmatched'
               and m.get('edge_index') is not None]
    if not edges or not matched:
        raise NotFoundError('road', 'the fixes matched no road', [])

    last = matched[-1]
    index = int(last['edge_index'])
    if not 0 <= index < len(edges):
        raise NotFoundError('road', 'matched an edge not in the answer', [])
    edge = edges[index]
    length = max(0.0, float(edge.get('length') or 0.0)) * 1000
    along = min(1.0, max(0.0, float(last.get('distance_along_edge') or 0.0)))
    return _limit(edge.get('speed_limit')), length * (1.0 - along)


class Limits:
    """What the daemon knows about the limit, fed every fix."""

    def __init__(self) -> None:
        self.on_change: Callable[[dict], None] | None = None
        self._published: dict | None = None
        self._reset_road()
        # The route the limits are being fetched for, and when to try
        # again after a failure.
        self._fetching: int | None = None
        self._route_retry_at = 0.0

    def _reset_road(self) -> None:
        self.road_limit: int | None = None
        self.road_known = False         # an answer has come for this road
        self._trail: deque[tuple[float, float]] = deque(maxlen=TRAIL_POINTS)
        self._driven = 0.0              # metres since the last answer
        self._valid = 0.0               # metres that answer covers
        self._asked_at = 0.0
        self._asked_heading: float | None = None
        self._asking = False
        self._last: tuple[float, float] | None = None

    # --- Every fix -----------------------------------------------------

    async def tick(self, reading: dict | None, session) -> None:
        """Called by the daemon's position watcher, about once a
        second. Never waits on the network."""
        if not settings.get_bool('speedlimit.show', True):
            self._publish({'shown': False, 'limit': None, 'source': None})
            return

        if session.active and session.route is not None \
                and session.state != 'arrived':
            self._route(session)
            return

        if not settings.get_bool('speedlimit.free', True):
            self._publish({'shown': False, 'limit': None, 'source': None})
            return

        self._road(reading)

    # --- Along a route -------------------------------------------------

    def _route(self, session) -> None:
        # The road's state is for when the route ends: start it afresh
        # then, rather than from wherever the car was when it began.
        if self.road_known or self._trail:
            self._reset_road()

        if session.limits is None:
            if self._fetching != session.version \
                    and time.time() >= self._route_retry_at:
                self._fetching = session.version
                asyncio.get_running_loop().create_task(
                    self._fetch_route(session, session.version))
            self._publish({'shown': True, 'limit': None, 'source': 'route'})
            return

        travelled = session.follower.progress.travelled \
            if session.follower else 0.0
        limit = None
        for start, end, kmh in session.limits:
            if start <= travelled < end:
                limit = kmh
                break
        else:
            # Past the end of the last span, by a rounding: its limit.
            if session.limits and travelled >= session.limits[-1][1]:
                limit = session.limits[-1][2]
        self._publish({'shown': True, 'limit': limit, 'source': 'route'})

    async def _fetch_route(self, session, version: int) -> None:
        try:
            spans = await spans_for(session.route)
        except (NotAvailableError, NotFoundError) as exc:
            log.info('speed limits: not for this route: %s',
                     str(exc).splitlines()[0])
            self._route_retry_at = time.time() + ROUTE_RETRY_SECONDS
        except Exception:
            log.exception('speed limits: fetching the route\'s failed')
            self._route_retry_at = time.time() + ROUTE_RETRY_SECONDS
        else:
            session.set_limits(version, spans)
        finally:
            if self._fetching == version:
                self._fetching = None

    # --- Without one ---------------------------------------------------

    def _road(self, reading: dict | None) -> None:
        live = (reading is not None and reading.get('source') == 'gps'
                and reading.get('latitude') is not None)
        if live:
            here = (reading['latitude'], reading['longitude'])
            if self._last is not None:
                self._driven += distance_metres(*self._last, *here)
            self._last = here
            if not self._trail or distance_metres(
                    *self._trail[-1], *here) >= TRAIL_SPACING:
                self._trail.append(here)

            kmh = float(reading.get('speed_kmh') or 0.0)
            heading = reading.get('heading')
            if kmh >= CRAWL_KMH and self._due(heading) \
                    and len(self._trail) >= 2 and not self._asking:
                self._asking = True
                self._asked_at = time.monotonic()
                asyncio.get_running_loop().create_task(
                    self._ask(list(self._trail), heading))

        # Believed for the stretch it covers, and a little past it when
        # asking again has not worked; unknown after that.
        stale = self.road_known and \
            self._driven > self._valid + STALE_METRES
        limit = None if stale else self.road_limit
        self._publish({'shown': True, 'limit': limit, 'source': 'road'})

    def _due(self, heading: float | None) -> bool:
        if time.monotonic() - self._asked_at < MIN_SECONDS:
            return False
        if not self.road_known:
            return True
        return (self._driven >= self._valid
                or self._driven >= MAX_METRES
                or _turned(self._asked_heading, heading))

    async def _ask(self, trail: list[tuple[float, float]],
                   heading: float | None) -> None:
        try:
            limit, left = await road_at(trail)
        except (NotAvailableError, NotFoundError) as exc:
            log.debug('speed limits: road not matched: %s',
                      str(exc).splitlines()[0])
        except Exception:
            log.exception('speed limits: matching the road failed')
        else:
            self.road_limit = limit
            self.road_known = True
            self._driven = 0.0
            self._valid = min(left, MAX_METRES)
            self._asked_heading = heading
        finally:
            self._asking = False

    # --- Out -----------------------------------------------------------

    def payload(self) -> dict:
        return self._published or {'shown': False, 'limit': None,
                                   'source': None}

    def _publish(self, data: dict) -> None:
        if data == self._published:
            return
        self._published = data
        if self.on_change:
            try:
                self.on_change(data)
            except Exception:
                log.exception('speed limits: publishing failed')


# The one the daemon keeps.
current = Limits()
