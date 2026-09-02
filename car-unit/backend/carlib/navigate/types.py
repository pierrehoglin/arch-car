"""
The route data model.

Valhalla's response is deeply nested and full of fields that only
matter for transit or bicycle costing. These types keep what a car
needs and give it names that read the same as the rest of carlib.
"""

import math
from dataclasses import dataclass, field, asdict

# Valhalla encodes shapes at six decimal places, not the five that
# Google's original polyline format uses. Decoding with the wrong
# precision puts the route in the sea off West Africa rather than
# failing, which is the sort of bug that takes an hour to spot.
POLYLINE_PRECISION = 6

EARTH_RADIUS = 6_371_000.0


def decode_polyline(encoded: str,
                    precision: int = POLYLINE_PRECISION
                    ) -> list[tuple[float, float]]:
    """
    Decode an encoded polyline into (latitude, longitude) pairs.

    The format stores deltas between successive points, each as a
    zigzag-encoded varint in chunks of five bits.
    """
    if not encoded:
        return []

    factor = float(10 ** precision)
    points: list[tuple[float, float]] = []

    index = 0
    lat = 0
    lon = 0
    length = len(encoded)

    while index < length:
        for axis in range(2):
            shift = 0
            result = 0
            while index < length:
                byte = ord(encoded[index]) - 63
                index += 1
                result |= (byte & 0x1F) << shift
                shift += 5
                if byte < 0x20:
                    break
            # The low bit is the sign, so a negative delta is stored
            # as its complement.
            delta = ~(result >> 1) if result & 1 else result >> 1
            if axis == 0:
                lat += delta
            else:
                lon += delta

        points.append((lat / factor, lon / factor))

    return points


def distance_metres(lat1: float, lon1: float,
                    lat2: float, lon2: float) -> float:
    """Great-circle distance, haversine."""
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)

    a = (math.sin(dphi / 2) ** 2
         + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2)
    return 2 * EARTH_RADIUS * math.asin(min(1.0, math.sqrt(a)))


def bearing_degrees(lat1: float, lon1: float,
                    lat2: float, lon2: float) -> float:
    """Initial bearing from one point to another, 0 = north."""
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dlambda = math.radians(lon2 - lon1)

    y = math.sin(dlambda) * math.cos(phi2)
    x = (math.cos(phi1) * math.sin(phi2)
         - math.sin(phi1) * math.cos(phi2) * math.cos(dlambda))
    return (math.degrees(math.atan2(y, x)) + 360.0) % 360.0


@dataclass
class Maneuver:
    """One instruction: a turn, a merge, an arrival."""

    kind: int = 0                   # Valhalla's numeric type
    instruction: str = ''
    verbal_pre: str = ''
    verbal_post: str = ''
    street: str = ''

    distance: float = 0.0           # km covered by this maneuver
    time: float = 0.0               # seconds

    # Where this maneuver sits in the leg's shape. The whole reason
    # for keeping it: without the index there is no way to say how far
    # away the turn is.
    begin_index: int = 0
    end_index: int = 0

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def distance_metres(self) -> float:
        return self.distance * 1000.0

    @property
    def label(self) -> str:
        return self.instruction or self.street or 'continue'


@dataclass
class Leg:
    """One stretch of route between two given points."""

    shape: list[tuple[float, float]] = field(default_factory=list)
    maneuvers: list[Maneuver] = field(default_factory=list)
    distance: float = 0.0           # km
    time: float = 0.0               # seconds

    def to_dict(self) -> dict:
        return {
            'shape': [list(p) for p in self.shape],
            'maneuvers': [m.to_dict() for m in self.maneuvers],
            'distance': self.distance,
            'time': self.time,
        }


@dataclass
class Route:
    """A complete route, as returned by the router."""

    legs: list[Leg] = field(default_factory=list)
    distance: float = 0.0           # km
    time: float = 0.0               # seconds
    summary: str = ''
    units: str = 'kilometers'
    costing: str = 'auto'

    def to_dict(self) -> dict:
        return {
            'legs': [leg.to_dict() for leg in self.legs],
            'distance': self.distance,
            'time': self.time,
            'summary': self.summary,
            'units': self.units,
            'costing': self.costing,
        }

    @property
    def shape(self) -> list[tuple[float, float]]:
        """Every point, legs joined end to end."""
        points: list[tuple[float, float]] = []
        for leg in self.legs:
            if points and leg.shape and points[-1] == leg.shape[0]:
                points.extend(leg.shape[1:])    # no duplicate join
            else:
                points.extend(leg.shape)
        return points

    @property
    def maneuvers(self) -> list[Maneuver]:
        """
        Every maneuver, with indices rebased onto the joined shape.

        Leg-local indices would point at the wrong place once the
        shapes are concatenated, which matters as soon as there is a
        waypoint.
        """
        result: list[Maneuver] = []
        offset = 0

        for leg in self.legs:
            for maneuver in leg.maneuvers:
                moved = Maneuver(**maneuver.to_dict())
                moved.begin_index += offset
                moved.end_index += offset
                result.append(moved)
            offset += max(0, len(leg.shape) - 1)

        return result

    @property
    def distance_metres(self) -> float:
        return self.distance * 1000.0

    @property
    def label(self) -> str:
        minutes = round(self.time / 60)
        if minutes >= 60:
            hours, minutes = divmod(minutes, 60)
            when = f'{hours} h {minutes:02d} min'
        else:
            when = f'{minutes} min'
        return f'{self.distance:.1f} km, {when}'


def parse_maneuver(payload: dict) -> Maneuver:
    names = payload.get('street_names') or []

    return Maneuver(
        kind=int(payload.get('type', 0) or 0),
        instruction=str(payload.get('instruction', '')),
        verbal_pre=str(payload.get('verbal_pre_transition_instruction',
                                   '')),
        verbal_post=str(
            payload.get('verbal_post_transition_instruction', '')),
        street=', '.join(str(n) for n in names),
        distance=float(payload.get('length', 0.0) or 0.0),
        time=float(payload.get('time', 0.0) or 0.0),
        begin_index=int(payload.get('begin_shape_index', 0) or 0),
        end_index=int(payload.get('end_shape_index', 0) or 0),
    )


def parse_route(payload: dict) -> Route:
    """
    Build a Route from a Valhalla /route or /trace_route response.

    Both wrap the useful part in `trip`, and the two are close enough
    in shape to share this.
    """
    trip = payload.get('trip') or payload

    legs = []
    for raw in trip.get('legs') or []:
        legs.append(Leg(
            shape=decode_polyline(raw.get('shape', '')),
            maneuvers=[parse_maneuver(m)
                       for m in raw.get('maneuvers') or []],
            distance=float((raw.get('summary') or {}).get('length', 0.0)
                           or 0.0),
            time=float((raw.get('summary') or {}).get('time', 0.0)
                       or 0.0),
        ))

    summary = trip.get('summary') or {}
    locations = trip.get('locations') or []
    names = [str(loc.get('name', '')) for loc in locations
             if loc.get('name')]

    return Route(
        legs=legs,
        distance=float(summary.get('length', 0.0) or 0.0),
        time=float(summary.get('time', 0.0) or 0.0),
        summary=' to '.join(names) if len(names) >= 2 else '',
        units=str(trip.get('units', 'kilometers')),
    )
