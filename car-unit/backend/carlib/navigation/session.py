"""
Navigating: following a route while the car drives it.

guidance.Follower knows where the car is along a route. This is the
rest of driving one: which turns are left and how far each is, the
stops on the way and when they have been passed, planning again when
the car leaves the route, arriving -- and keeping the route on disk so
that turning the car off for a break does not lose it.

One session, held by the daemon: navigation carries on whichever
screen is open, and every screen sees the same one through the
'navigation' event.

States:

    idle        nothing to follow
    resuming    a saved route, loaded at start-up, waiting for a fix
    navigating  following the route
    rerouting   off the route; a new one is being asked for
    offline     off the route, and no new one to be had -- no signal,
                or no road. Asked again every RETRY_SECONDS
    arrived     at the destination
"""

import asyncio
import json
import logging
import os
import time
from pathlib import Path
from typing import Callable

from carlib.core import settings
from carlib.core.errors import NotAvailableError, NotFoundError
from carlib.navigation import routing
from carlib.navigation.guidance import (
    DEFAULT_OFF_ROUTE_FIXES, DEFAULT_OFF_ROUTE_METRES, Follower, Progress,
)
from carlib.navigation.types import Route, distance_metres

log = logging.getLogger('carlib')

# Close enough to the destination to call it reached. GPS error and
# where exactly the router put the end of the road both fit inside it.
ARRIVE_METRES = 30.0

# Close enough to a stop to count it as visited. A little more than
# arriving: a stop is often a car park beside the road, not on it.
STOP_METRES = 40.0

# The turn after the next is shown as "then" when it comes this soon
# after -- close enough that there is no time to read it later.
THEN_METRES = 200.0

# Between attempts to plan again while off the route and failing.
RETRY_SECONDS = 15.0


def state_file() -> Path:
    """Where the route being driven is kept between runs."""
    base = os.environ.get('XDG_DATA_HOME')
    root = Path(base) if base else Path.home() / '.local' / 'share'
    return root / 'carlib' / 'navigation.json'


def _shape(route: Route) -> list[list[float]]:
    """[lon, lat] for GeoJSON, to about a metre."""
    return [[round(lon, 5), round(lat, 5)] for lat, lon in route.shape]


class Session:
    def __init__(self) -> None:
        # Told every time what the screens should show has changed.
        self.on_change: Callable[[dict], None] | None = None
        # Counts route replacements across the life of the daemon, so a
        # screen can tell a new route from the same one again.
        self.version = 0
        self._reset()

    def _reset(self) -> None:
        self.state = 'idle'
        self.destination: dict | None = None
        # The stops still to visit, in order.
        self.stops: list[dict] = []
        # How far along the route each of those stops is, in metres.
        self.stop_ends: list[float] = []
        self.route: Route | None = None
        self.follower: Follower | None = None
        self.resumed = False
        self.message = ''
        self.retry_at = 0.0
        self._rerouting = False
        self._step: int | None = None
        self._published: dict | None = None
        # Bumped by end(), so a reroute finishing after it is dropped.
        self._generation = getattr(self, '_generation', 0) + 1

    @property
    def active(self) -> bool:
        return self.state != 'idle'

    # --- The route ---------------------------------------------------

    def _set_route(self, route: Route, destination: dict,
                   stops: list[dict]) -> None:
        self.route = route
        self.follower = Follower(
            route,
            off_route_metres=settings.get_float(
                'navigation.off_route_metres', DEFAULT_OFF_ROUTE_METRES),
            off_route_fixes=int(settings.get_float(
                'navigation.off_route_fixes', DEFAULT_OFF_ROUTE_FIXES)))
        self.destination = dict(destination)
        self.stops = [dict(s) for s in stops]

        # A stop is reached at the end of its leg. Counted the way
        # Route.maneuvers rebases its indices, so they agree. The legs
        # of stops already passed are still in a route kept from
        # before, so the remaining stops are the last ones.
        totals = self.follower.totals
        ends, index = [], 0
        for leg in route.legs[:-1]:
            index += max(0, len(leg.shape) - 1)
            ends.append(totals[min(index, len(totals) - 1)] if totals else 0.0)
        self.stop_ends = ends[len(ends) - len(self.stops):] if self.stops else []

        self.version += 1
        self._step = None

    def _progress_at(self, index: int) -> Progress:
        """Where the car would be at a point on the route, before any
        fix has said so -- for a route just resumed."""
        follower = self.follower
        totals = follower.totals
        index = max(0, min(index, len(totals) - 1)) if totals else 0
        travelled = totals[index] if totals else 0.0
        remaining = max(0.0, follower.total_metres - travelled)
        current, following = follower._maneuver_at(index)
        share = remaining / follower.total_metres if follower.total_metres else 0
        return Progress(
            index=index, travelled=travelled, remaining=remaining,
            remaining_time=self.route.time * share,
            maneuver=current, next_maneuver=following,
            next_distance=(max(0.0, totals[following.begin_index] - travelled)
                           if following and following.begin_index < len(totals)
                           else 0.0))

    def start(self, route: Route, destination: dict, stops: list[dict],
              reading: dict | None = None) -> None:
        """Begin following a route, from wherever the car is."""
        self._reset()
        self._set_route(route, destination, stops)
        self.state = 'navigating'
        if reading is not None and _live(reading):
            self.follower.update(reading['latitude'], reading['longitude'])
        self._save()
        self._publish()

    def replace(self, route: Route, destination: dict,
                stops: list[dict]) -> None:
        """A new route while driving: a new destination, or stops
        added or taken away. Planned from where the car is now."""
        self._set_route(route, destination, stops)
        self.state = 'navigating'
        self.message = ''
        self._save()
        self._publish()

    def end(self) -> None:
        """Stop navigating, and forget the route -- here and on disk."""
        self._forget()
        self._reset()
        self.version += 1
        self._publish()

    # --- Every fix ---------------------------------------------------

    async def tick(self, reading: dict | None) -> None:
        """
        Take the latest position and say what has changed.

        Called by the daemon's position watcher, about once a second.
        Never waits on the network: planning again runs as a task of
        its own, so the position keeps flowing while it does.
        """
        if self.state in ('idle', 'arrived') or self.follower is None:
            return
        # A remembered position is not where the car is now. In a
        # tunnel the guidance holds still rather than act on it.
        if not _live(reading):
            return

        lat, lon = reading['latitude'], reading['longitude']
        progress = self.follower.update(lat, lon)

        if self.state == 'resuming':
            # Back on the road where it left off, or somewhere else --
            # a car park beside it, mostly -- and a new way from there.
            if progress.on_route:
                self.state = 'navigating'
                self.message = ''
            else:
                self._spawn_reroute(lat, lon)
                self._publish()
                return

        if self.state in ('rerouting', 'offline'):
            if progress.on_route and not self._rerouting:
                # Found its own way back.
                self.state = 'navigating'
                self.message = ''
            elif self.state == 'offline' and time.time() >= self.retry_at:
                self._spawn_reroute(lat, lon)
            self._publish()
            return

        if self._arrived(lat, lon, progress):
            self.state = 'arrived'
            self.message = ''
            self._forget()
            self._publish()
            return

        if self._passed_stops(lat, lon, progress):
            self._save()

        if self.follower.needs_reroute:
            self._spawn_reroute(lat, lon)

        # Saved as each turn is passed, not every second: often enough
        # to come back to the right stretch of road, rarely enough to
        # spare the SD card.
        step = progress.next_maneuver.begin_index if progress.next_maneuver else -1
        if step != self._step:
            self._step = step
            self._save()

        self._publish()

    def _arrived(self, lat: float, lon: float, progress: Progress) -> bool:
        goal = self.destination
        if distance_metres(lat, lon, goal['latitude'],
                           goal['longitude']) <= ARRIVE_METRES:
            return True
        return (not self.stops and progress.on_route
                and progress.remaining <= ARRIVE_METRES)

    def _passed_stops(self, lat: float, lon: float,
                      progress: Progress) -> bool:
        """Drop the stops the car has reached or gone past."""
        passed = False
        while self.stops:
            stop = self.stops[0]
            near = distance_metres(lat, lon, stop['latitude'],
                                   stop['longitude']) <= STOP_METRES
            beyond = (progress.on_route and self.stop_ends
                      and progress.travelled >= self.stop_ends[0] - STOP_METRES)
            if not (near or beyond):
                break
            self.stops.pop(0)
            if self.stop_ends:
                self.stop_ends.pop(0)
            passed = True
        return passed

    # --- Off the route -------------------------------------------------

    def _spawn_reroute(self, lat: float, lon: float) -> None:
        if self._rerouting:
            return
        self._rerouting = True
        self.state = 'rerouting'
        self.message = 'Rerouting…'
        asyncio.get_running_loop().create_task(
            self._reroute(lat, lon, self._generation))

    async def _reroute(self, lat: float, lon: float,
                       generation: int) -> None:
        points = [(lat, lon),
                  *[(s['latitude'], s['longitude']) for s in self.stops],
                  (self.destination['latitude'],
                   self.destination['longitude'])]
        try:
            found = await routing.plan(points, alternates=0)
        except (NotAvailableError, NotFoundError) as exc:
            if generation != self._generation:
                return
            self.state = 'offline'
            self.retry_at = time.time() + RETRY_SECONDS
            self.message = (
                "Off route — can't reroute without a connection"
                if isinstance(exc, NotAvailableError)
                else 'Off route — no road route from here')
            log.info('navigation: reroute failed: %s',
                     str(exc).splitlines()[0])
        except Exception:
            log.exception('navigation: reroute failed')
            if generation == self._generation:
                self.state = 'offline'
                self.retry_at = time.time() + RETRY_SECONDS
                self.message = 'Off route — rerouting failed'
        else:
            if generation != self._generation:
                return
            self._set_route(found[0], self.destination, self.stops)
            self.state = 'navigating'
            self.message = ''
            self._save()
            log.info('navigation: rerouted, %s', found[0].label)
        finally:
            if generation == self._generation:
                self._rerouting = False
                self._publish()

    # --- What the screens get ------------------------------------------

    def payload(self) -> dict:
        """The 'navigation' event: everything a screen shows, small
        enough to send every second. The route's line is not in it --
        see detail()."""
        if self.state == 'idle' or self.follower is None:
            return {'state': 'idle', 'version': self.version}

        progress = self.follower.progress
        totals = self.follower.totals

        steps = []
        if self.state != 'arrived':
            steps = self._steps(progress, totals)

        following = (steps[1] if len(steps) > 1
                     and steps[1]['distance'] - steps[0]['distance']
                     <= THEN_METRES else None)

        return {
            'state': self.state,
            'version': self.version,
            'resumed': self.resumed,
            'message': self.message,
            'destination': self.destination,
            'stops': self.stops,
            'remaining': round(progress.remaining),
            'remaining_time': round(progress.remaining_time),
            'next': steps[0] if steps else None,
            'then': following,
            'steps': steps,
            'on_route': progress.on_route,
            'snapped': ({'latitude': round(progress.latitude, 6),
                         'longitude': round(progress.longitude, 6),
                         'bearing': (round(progress.bearing)
                                     if progress.bearing is not None
                                     else None)}
                        if progress.on_route and progress.latitude
                        else None),
            'index': progress.index,
        }

    # Valhalla's arrival maneuvers: at the destination, and at the end
    # of every leg -- which is to say at every stop.
    ARRIVALS = (4, 5, 6)

    def _steps(self, progress: Progress, totals: list[float]) -> list[dict]:
        """
        Every turn still ahead, with how far each is from the car.

        A stop's arrival is a step of its own, numbered as the stop is,
        until the stop has been passed -- after which it is dropped:
        "You have arrived" for somewhere already left behind would be
        the next thing on the screen.
        """
        maneuvers = self.follower.maneuvers
        final = maneuvers[-1] if maneuvers else None
        ahead = [m for m in maneuvers
                 if m.begin_index > progress.index
                 and m.begin_index < len(totals)]

        stop_arrivals = [m for m in ahead
                         if m.kind in self.ARRIVALS and m is not final]
        # The remaining stops are the last of them; any earlier ones
        # belong to stops already passed.
        keep = stop_arrivals[len(stop_arrivals) - len(self.stops):] \
            if self.stops else []
        numbers = {id(m): n for n, m in enumerate(keep, start=1)}

        steps = []
        for m in ahead:
            intermediate = m.kind in self.ARRIVALS and m is not final
            if intermediate and id(m) not in numbers:
                continue
            step = {
                'kind': m.kind,
                'instruction': m.instruction,
                'street': m.street,
                'distance': round(max(0.0, totals[m.begin_index]
                                      - progress.travelled)),
            }
            if intermediate:
                number = numbers[id(m)]
                step['stop'] = number
                step['title'] = self.stops[number - 1].get('title', '')
            steps.append(step)
        return steps

    def detail(self) -> dict:
        """The payload and the route's line: for a screen opening, and
        once after every new route."""
        data = self.payload()
        data['shape'] = _shape(self.route) if self.route and self.active else []
        return data

    def _publish(self) -> None:
        data = self.payload()
        if data == self._published:
            return
        self._published = data
        if self.on_change:
            try:
                self.on_change(data)
            except Exception:
                log.exception('navigation: publishing failed')

    # --- Keeping it between runs ---------------------------------------

    def _save(self) -> None:
        if self.route is None or self.state in ('idle', 'arrived'):
            return
        data = {
            'saved_at': time.time(),
            'destination': self.destination,
            'stops': self.stops,
            'route': self.route.to_dict(),
            'index': self.follower.index if self.follower else 0,
        }
        path = state_file()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            # Written beside and swapped in, so the car losing power
            # mid-write leaves the last good copy rather than half of
            # a new one.
            partial = path.with_suffix('.json.partial')
            partial.write_text(json.dumps(data))
            os.replace(partial, path)
        except OSError:
            log.exception('navigation: could not save the route')

    def _forget(self) -> None:
        try:
            state_file().unlink(missing_ok=True)
        except OSError:
            pass

    def resume(self) -> bool:
        """
        Pick up a route saved before the car was turned off.

        Not when resuming is turned off, and not a route older than
        navigation.resume_hours -- yesterday's drive is not what
        anyone wants to see this morning. Either way the file goes.
        """
        path = state_file()
        if not path.exists():
            return False

        try:
            data = json.loads(path.read_text())
        except (OSError, ValueError):
            self._forget()
            return False

        limit = settings.get_float('navigation.resume_hours', 24.0) * 3600
        age = time.time() - float(data.get('saved_at', 0))
        if not settings.get_bool('navigation.resume', True) or age > limit:
            self._forget()
            return False

        try:
            route = Route.from_dict(data['route'])
            self._reset()
            self._set_route(route, data['destination'], data.get('stops') or [])
        except (KeyError, TypeError, ValueError):
            log.warning('navigation: the saved route could not be read')
            self._forget()
            self._reset()
            return False

        self.follower.index = int(data.get('index', 0) or 0)
        self.follower.progress = self._progress_at(self.follower.index)
        self.state = 'resuming'
        self.resumed = True
        self.message = 'Resuming route · waiting for GPS'
        log.info('navigation: resuming the route to %s',
                 self.destination.get('title', 'the destination'))
        self._publish()
        return True


def _live(reading: dict | None) -> bool:
    """A position worth navigating by: a live fix, or a pin on the
    bench. Not the remembered one used while the GPS starts."""
    return (reading is not None
            and reading.get('source') in ('gps', 'pin')
            and reading.get('latitude') is not None
            and reading.get('longitude') is not None)


# The one session the daemon drives.
current = Session()
