"""
Following a route.

Where we are along it, which instruction is next, and whether we have
left it. This is the part that makes a drawn line into navigation.

Nothing here talks to a router. It works on a Route and a position, so
it costs nothing to run on every GPS fix and can be tested without a
network.
"""

import math
from dataclasses import dataclass, field, asdict

from carlib.navigation.types import (
    Route, Maneuver, distance_metres, EARTH_RADIUS,
)

# How far off the line before we call it off-route. Generous enough to
# absorb GPS error and a dual carriageway's second lane; tight enough
# to notice a missed exit.
DEFAULT_OFF_ROUTE_METRES = 50.0

# And for how many fixes in a row. A single bad fix under a bridge
# should not trigger a reroute, and waiting three seconds costs
# nothing when the alternative is recalculating for no reason.
DEFAULT_OFF_ROUTE_FIXES = 3

# How far ahead to look when finding our position on the route.
# Searching the whole shape every fix is wasteful on a long route, and
# worse, it can jump to a later stretch that happens to pass close by
# -- a motorway beside the road you are on, or a return leg.
SEARCH_WINDOW = 400


@dataclass
class Progress:
    """Where we are on a route."""

    on_route: bool = True
    off_route_metres: float = 0.0       # distance from the line

    # Snapped position: the nearest point on the route. Showing this
    # rather than the raw fix is what keeps the marker on the road.
    latitude: float = 0.0
    longitude: float = 0.0

    index: int = 0                      # segment we are on
    travelled: float = 0.0              # metres covered
    remaining: float = 0.0              # metres left
    remaining_time: float = 0.0         # seconds, estimated

    maneuver: Maneuver | None = None        # the one being driven
    next_maneuver: Maneuver | None = None   # the one to announce
    next_distance: float = 0.0          # metres to it

    bearing: float | None = None        # direction of travel on route

    def to_dict(self) -> dict:
        data = asdict(self)
        data['maneuver'] = self.maneuver.to_dict() if self.maneuver else None
        data['next_maneuver'] = (self.next_maneuver.to_dict()
                                 if self.next_maneuver else None)
        return data

    @property
    def remaining_km(self) -> float:
        return self.remaining / 1000.0

    @property
    def label(self) -> str:
        if not self.on_route:
            return f'off route by {self.off_route_metres:.0f} m'

        minutes = round(self.remaining_time / 60)
        parts = [f'{self.remaining_km:.1f} km', f'{minutes} min']

        if self.next_maneuver is not None:
            distance = self.next_distance
            near = (f'{distance:.0f} m' if distance < 1000
                    else f'{distance / 1000:.1f} km')
            parts.append(f'{self.next_maneuver.label} in {near}')

        return '  '.join(parts)


def _project(lat: float, lon: float, lat0: float) -> tuple[float, float]:
    """
    Local planar coordinates in metres.

    Equirectangular about a reference latitude. Over the few hundred
    metres this is used for, the error is far below GPS noise, and it
    turns the point-to-segment problem into simple arithmetic.
    """
    x = math.radians(lon) * math.cos(math.radians(lat0)) * EARTH_RADIUS
    y = math.radians(lat) * EARTH_RADIUS
    return x, y


def point_on_segment(lat: float, lon: float,
                     lat1: float, lon1: float,
                     lat2: float, lon2: float
                     ) -> tuple[float, float, float, float]:
    """
    Nearest point on a segment to a position.

    Returns (latitude, longitude, distance in metres, fraction along).
    The fraction is clamped, so a position past either end snaps to
    that end rather than to an imaginary extension of the road.
    """
    px, py = _project(lat, lon, lat)
    ax, ay = _project(lat1, lon1, lat)
    bx, by = _project(lat2, lon2, lat)

    dx, dy = bx - ax, by - ay
    length_squared = dx * dx + dy * dy

    if length_squared == 0.0:
        return lat1, lon1, distance_metres(lat, lon, lat1, lon1), 0.0

    t = ((px - ax) * dx + (py - ay) * dy) / length_squared
    t = max(0.0, min(1.0, t))

    snapped_lat = lat1 + (lat2 - lat1) * t
    snapped_lon = lon1 + (lon2 - lon1) * t

    return (snapped_lat, snapped_lon,
            distance_metres(lat, lon, snapped_lat, snapped_lon), t)


def locate(shape: list[tuple[float, float]],
           latitude: float, longitude: float,
           from_index: int = 0,
           window: int = SEARCH_WINDOW
           ) -> tuple[int, float, float, float, float]:
    """
    Find where a position sits on a shape.

    Returns (segment index, snapped lat, snapped lon, distance from
    the line, fraction along that segment).

    Searching forward from the last known index rather than the whole
    shape: it is faster, and it stops the position jumping to a
    different part of the route that happens to run nearby -- the
    opposite carriageway, or a road crossed earlier.
    """
    if len(shape) < 2:
        if shape:
            return (0, shape[0][0], shape[0][1],
                    distance_metres(latitude, longitude,
                                    shape[0][0], shape[0][1]), 0.0)
        return 0, latitude, longitude, 0.0, 0.0

    start = max(0, min(from_index, len(shape) - 2))
    end = min(len(shape) - 1, start + window)

    best = (start, shape[start][0], shape[start][1], float('inf'), 0.0)

    for index in range(start, end):
        lat1, lon1 = shape[index]
        lat2, lon2 = shape[index + 1]
        snapped_lat, snapped_lon, gap, t = point_on_segment(
            latitude, longitude, lat1, lon1, lat2, lon2)

        if gap < best[3]:
            best = (index, snapped_lat, snapped_lon, gap, t)

    return best


def cumulative(shape: list[tuple[float, float]]) -> list[float]:
    """Distance from the start to each point, in metres."""
    totals = [0.0]
    for index in range(1, len(shape)):
        totals.append(totals[-1] + distance_metres(
            shape[index - 1][0], shape[index - 1][1],
            shape[index][0], shape[index][1]))
    return totals


class Follower:
    """
    Tracks progress along one route.

    Holds the last position so each fix searches forward rather than
    over the whole shape, and counts consecutive off-route fixes so a
    single bad one does not trigger a reroute.

        follower = Follower(route)
        progress = follower.update(lat, lon)
        if follower.needs_reroute:
            ...
    """

    def __init__(self, route: Route,
                 off_route_metres: float = DEFAULT_OFF_ROUTE_METRES,
                 off_route_fixes: int = DEFAULT_OFF_ROUTE_FIXES):
        self.route = route
        self.shape = route.shape
        self.maneuvers = route.maneuvers
        self.totals = cumulative(self.shape)
        self.off_route_metres = off_route_metres
        self.off_route_fixes = off_route_fixes

        self.index = 0
        self.strikes = 0
        self.progress = Progress()

    @property
    def total_metres(self) -> float:
        return self.totals[-1] if self.totals else 0.0

    @property
    def needs_reroute(self) -> bool:
        """True once we have been off the line for enough fixes."""
        return self.strikes >= self.off_route_fixes

    def _maneuver_at(self, index: int
                     ) -> tuple[Maneuver | None, Maneuver | None]:
        """The maneuver being driven, and the one after it."""
        current = None
        following = None

        for position, maneuver in enumerate(self.maneuvers):
            if maneuver.begin_index <= index < maneuver.end_index:
                current = maneuver
                if position + 1 < len(self.maneuvers):
                    following = self.maneuvers[position + 1]
                break
        else:
            # Past the last maneuver's range, which happens at the
            # very end of the route.
            if self.maneuvers:
                current = self.maneuvers[-1]

        return current, following

    def update(self, latitude: float, longitude: float) -> Progress:
        """Take a GPS fix and say where we are."""
        if len(self.shape) < 2:
            return self.progress

        index, snapped_lat, snapped_lon, gap, fraction = locate(
            self.shape, latitude, longitude, self.index)

        on_route = gap <= self.off_route_metres

        # Only advance when on the line. A position that has left the
        # route should not drag the search window along with it, or
        # returning to the route later would look like a jump forward.
        if on_route:
            self.index = index
            self.strikes = 0
        else:
            self.strikes += 1

        segment_length = (self.totals[index + 1] - self.totals[index]
                          if index + 1 < len(self.totals) else 0.0)
        travelled = self.totals[index] + segment_length * fraction
        remaining = max(0.0, self.total_metres - travelled)

        current, following = self._maneuver_at(index)

        next_distance = 0.0
        if following is not None and following.begin_index < len(self.totals):
            next_distance = max(
                0.0, self.totals[following.begin_index] - travelled)

        bearing = None
        if index + 1 < len(self.shape):
            from carlib.navigation.types import bearing_degrees
            lat1, lon1 = self.shape[index]
            lat2, lon2 = self.shape[index + 1]
            bearing = bearing_degrees(lat1, lon1, lat2, lon2)

        # Time left, scaled by how much distance is left. Cruder than
        # summing the remaining maneuvers, but it does not lurch when
        # a maneuver boundary is crossed.
        share = (remaining / self.total_metres
                 if self.total_metres > 0 else 0.0)

        self.progress = Progress(
            on_route=on_route,
            off_route_metres=gap,
            latitude=snapped_lat,
            longitude=snapped_lon,
            index=index,
            travelled=travelled,
            remaining=remaining,
            remaining_time=self.route.time * share,
            maneuver=current,
            next_maneuver=following,
            next_distance=next_distance,
            bearing=bearing,
        )
        return self.progress
