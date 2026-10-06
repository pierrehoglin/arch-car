"""
The carlib daemon.

Owns runtime state and runs the source supervisor, serving everything
else over a Unix socket:

    uvicorn carlib.api.main:app --uds $XDG_RUNTIME_DIR/carlib.sock

Deliberately thin. Every route calls a function in routes.py, which
has no framework imports and can be tested directly -- so a mistake
here is a wiring mistake, visible immediately, rather than a logic
bug hidden behind a web server.

The Unix socket keeps CLI traffic off the network entirely. For a
browser UI, add a TCP listener bound to localhost:

    uvicorn carlib.api.main:app --host 127.0.0.1 --port 8099

Bind to 127.0.0.1 and not 0.0.0.0: the hotspot runs on this machine,
and passengers should not be able to change stations.
"""

import time
import asyncio
import logging
import contextlib
from pathlib import Path

from fastapi import APIRouter, FastAPI, Request, Response
from fastapi.responses import (FileResponse, JSONResponse,
                               StreamingResponse)
from pydantic import BaseModel

from carlib.core import settings, state
from carlib.core.errors import CarError, NotFoundError
from carlib.api import events, routes
from carlib.bluetooth.pairing import Pairing
from carlib.location import geocoding, places, position
from carlib.navigation import tiles, download, session
from carlib.radio import fm
from carlib.system import audio, source

log = logging.getLogger('carlib')

_supervisor: asyncio.Task | None = None
_autostart_task: asyncio.Task | None = None
_geocoder: asyncio.Task | None = None
_audio_watch: asyncio.Task | None = None
_bluetooth_watch: asyncio.Task | None = None
_media_watch: asyncio.Task | None = None
_network_watch: asyncio.Task | None = None
_fm_watch: asyncio.Task | None = None

# How often to look at what is playing. Often enough that a track
# change on the phone reaches the screen before the song does,
# rarely enough to be free -- each pass is two subprocess calls.
MEDIA_POLL = 2.0

# Slower than the rest. Each pass shells out to nmcli and hostapd_cli,
# and the answer changes when somebody drives out of range, not
# between one second and the next.
NETWORK_POLL = 5.0

# Reading the radio is a file and a process check, and radiotext
# scrolls at walking pace -- a second is plenty, and anything faster
# would be a poll per scroll step for no gain.
FM_POLL = 1.0

# How far a position may differ from where it should have got to
# before it counts as a seek rather than the track playing on.
#
# signature() leaves position out, because it moves every second by
# definition and comparing it would publish constantly. But a seek is
# a real change the screen has to hear about, and the way to tell the
# two apart is that playing on is predictable and a seek is not.
#
# Generous, because a pass can be late: a command settling, or the
# daemon busy elsewhere, both stretch the interval.
SEEK_TOLERANCE = 4.0

# The daemon's one pairing session: the agent, the window, and
# whatever is waiting on an answer. Created here, and only here,
# so that importing carlib never registers an agent by accident.
pairing = Pairing(events.events.publish)


async def _run_supervisor() -> None:
    """
    Source arbitration, in-process.

    This has to live here rather than in its own service: the
    supervisor and the API both read and write source state, and two
    processes doing that is exactly the lost-update problem the daemon
    exists to remove.
    """
    while True:
        try:
            async for event in source.supervise():
                log.info('source: %s%s%s',
                         event.active or 'nothing',
                         ' [traffic]' if event.traffic else '',
                         f' (paused {", ".join(event.paused)})'
                         if event.paused else '')
        except asyncio.CancelledError:
            raise
        except Exception:
            # A supervisor that dies silently would leave sources
            # unarbitrated with no sign anything is wrong.
            log.exception('source supervisor failed; restarting in 5s')
            await asyncio.sleep(5)


async def _autostart() -> None:
    """
    Start the radio at boot, if `fm.autostart` is set.

    A background task rather than part of startup: the pipeline needs
    a second and a half to prove itself, and the daemon should be
    answering requests before then. A missing dongle should also not
    stop the daemon from running.

    This replaces a systemd unit that ran `fm play` after the daemon.
    That needed Requires=, a start limit, and still failed noisily
    when it raced the socket -- all of which the daemon already knows
    how to avoid, since it owns the pipeline anyway.
    """
    if not settings.get_bool('fm.autostart', False):
        return

    try:
        state_ = await fm.play()
    except CarError as exc:
        # Worth a warning, not a failure. The rest of the daemon works
        # without a radio.
        log.warning('autostart: %s', str(exc).splitlines()[0])
        return
    except Exception:
        log.exception('autostart failed unexpectedly')
        return

    if state_.frequency is not None:
        log.info('autostart: radio on %.1f MHz', state_.frequency)


# How often the place tracker looks at the position. Looking costs
# nothing -- the reading is already there, taken by the position
# watcher -- and only a real move past the geocoder's thresholds turns
# into a request.
PLACE_POLL = 5.0


async def _watch_place() -> None:
    """
    Keep the current address up to date, and publish it when it
    changes.

    Two jobs in one loop, because they share a position and a pace:

    Looking the address up as the car moves, when `geocoding.auto` is
    on. Nominatim is a third-party service with a usage policy, so this
    stays a deliberate choice -- the geocoder's distance thresholds and
    its per-minute budget decide when a move is worth a request. Here
    rather than in its own service because the rate limit applies
    across the whole application.

        settings set geocoding.auto true

    Publishing a 'place' event whenever what the car's position is
    called changes: a new address, an address no longer close enough
    to count, or the fix being lost or found. With auto off, addresses
    still arrive from lookups a screen asks for -- /places/current --
    and are published from here the same way.

    Uses the position watcher's latest reading rather than the GPS, so
    the modem is read in one place.
    """
    published: dict | None = None

    while True:
        try:
            reading = position.latest()
            if position.located(reading):
                if settings.get_bool('geocoding.auto', False):
                    try:
                        fresh = await geocoding.update_current(
                            reading['latitude'], reading['longitude'])
                        if fresh is not None:
                            log.info('location: %s', fresh.short)
                    except Exception as exc:
                        # No signal, mostly. The address stays as it
                        # was and the next move tries again.
                        log.debug('geocoder: %s', exc)

                described = position.describe(
                    reading, position.address_for(reading))
                if not position.same_place(described, published):
                    published = described
                    events.events.publish('place', described)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception('place watch failed')

        await asyncio.sleep(PLACE_POLL)


# How often the GPS is read to keep the last known position. Writes
# are rarer -- places.remember() decides -- so this only sets how soon
# a stop is noticed.
REMEMBER_POLL = 15.0


async def _remember_position() -> None:
    """
    Keep the last GPS fix in the settings file.

    So that after a power cut there is a position straight away rather
    than none until the GPS has found its satellites again. Separate
    from the geocoder because that one is off by default, and this
    needs no network.

    Skipped while the position is pinned: there is nothing to remember
    that the pin does not already say.
    """
    from carlib.location import gps

    while True:
        await asyncio.sleep(REMEMBER_POLL)

        if settings.get('location.latitude') is not None:
            continue

        try:
            fix = await gps.get()
        except Exception:
            continue

        if (not fix.has_fix or fix.latitude is None
                or fix.longitude is None):
            continue

        # The geocoder's address, when it was looked up close by. A
        # remembered position with a name reads better after a restart
        # than a pair of numbers.
        address = ''
        tracked = places.current()
        if tracked is not None and tracked.address:
            if places._metres(tracked.latitude, tracked.longitude,
                              fix.latitude, fix.longitude) < 500:
                address = tracked.address

        try:
            places.remember(fix.latitude, fix.longitude,
                            fix.altitude, address)
        except Exception:
            log.exception('could not save the last known position')


# How often the position is read for the map. The GPS service sets the
# modem to refresh once a second, so reading faster finds nothing new,
# and reading slower makes the car jump along the road.
POSITION_POLL = 1.0


async def _watch_position() -> None:
    """
    Publish where the car is, as it moves.

    Polled: ModemManager can signal changes, but that subscription
    dies with ModemManager, and the reason gps-supervise exists is that
    ModemManager restarts. Published only when the reading would draw
    differently, so a parked car is quiet.
    """
    last: dict | None = None

    while True:
        try:
            reading = await position.read()
            if not position.same(reading, last):
                last = reading
                events.events.publish('position', reading)

            # Guidance follows every reading, not only changed ones: a
            # car stopped at a junction still needs its distances. It
            # publishes only what has changed.
            await session.current.tick(reading)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception('position watch failed')

        await asyncio.sleep(POSITION_POLL)


async def _watch_audio() -> None:
    """
    Publish the volume whenever it changes.

    Anything can move it -- the CLI, another program, the steering
    wheel once CAN is wired -- and a UI that only saw its own changes
    would drift the first time something else did.

    Restarted on failure rather than given up on: pactl going away
    means pipewire-pulse restarted, which it may well do, and the
    stream should come back with it.
    """
    while True:
        try:
            async for reading in audio.watch():
                events.events.publish('audio', reading.to_dict())
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception('audio watch failed; retrying in 10s')
            await asyncio.sleep(10)


async def _watch_fm() -> None:
    """
    Publish the radio's state as it changes.

    RDS is the reason this exists. A station's name arrives a second
    or two after tuning, and its radiotext changes while you listen --
    neither is a thing anyone presses a button for, so without a
    watcher the screen shows whatever was true when it last asked.

    Faster than the network watcher and slower than audio: reading
    the state is a file and a process check, and radiotext scrolls at
    walking pace.
    """
    # Presets once, at the start. They change only when somebody
    # edits them, so nothing would otherwise fill the replay cache --
    # and a screen opening before the first edit would find nothing
    # waiting for it.
    with contextlib.suppress(Exception):
        events.events.publish(
            'presets', [s.to_dict() for s in fm.load_presets()])

    last: dict | None = None

    while True:
        try:
            state = (await fm.status()).to_dict()
            if state != last:
                last = state
                events.events.publish('fm', state)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception('fm watch failed')

        await asyncio.sleep(FM_POLL)


async def _watch_network() -> None:
    """
    Publish the radio's state when it changes.

    Polled, and slowly. Neither nmcli nor hostapd offers anything to
    subscribe to, and this is a thing that changes when somebody
    drives out of range or flips a switch -- not second by second.
    """
    last: dict | None = None

    while True:
        try:
            state = await routes.network_status()
            if state != last:
                last = state
                events.events.publish('network', state)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception('network watch failed')

        await asyncio.sleep(NETWORK_POLL)


async def _watch_media() -> None:
    """
    Publish what each source is playing.

    Polled rather than pushed: neither AVRCP nor MPRIS signals a
    position change, and a track change arrives as a property update
    we would have to subscribe to twice, once per transport. Reading
    both on a timer is less machinery for the same result.

    Reporting only. Deciding which source wins belongs to
    source.supervise(), which sees FM and the phone and every
    MPRIS player at once -- two arbiters would take turns undoing
    each other.

    Position is deliberately left out of the comparison. It moves
    every second by definition, and publishing on it would be a
    message a second for the life of the ignition -- the screen
    extrapolates instead, from the last reading and the status.
    """
    last: dict[str, tuple] = {}

    # Position, and when it was read, for telling a seek from the
    # track simply playing on.
    seen: dict[str, tuple[int, float, bool]] = {}

    while True:
        try:
            for which in (source.BLUETOOTH, source.SPOTIFY):
                try:
                    playing = await source.now_playing(which)
                except CarError:
                    continue

                # The same comparison the command uses to decide a
                # player has caught up. Two definitions of "changed"
                # would mean a command that returned fresh state the
                # watcher then declined to publish.
                signature = source.signature(playing)

                moved = _seeked(which, playing, seen)

                if last.get(which) == signature and not moved:
                    continue

                last[which] = signature
                events.events.publish('media', playing.to_dict())


        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception('media watch failed')

        await asyncio.sleep(MEDIA_POLL)


def _seeked(which: str, playing: object, seen: dict) -> bool:
    """
    Whether the position moved further than playing explains.

    Somebody dragging the bar, or `playerctl position`, changes
    nothing else about the player -- same track, same status -- so
    without this the screen keeps showing where the track was before
    the jump until it happens to change some other way.
    """
    position = getattr(playing, 'position', None)
    now = time.monotonic()

    before = seen.get(which)
    seen[which] = ((position, now, playing.status == 'playing')
                   if position is not None else (0, now, False))

    if position is None or before is None:
        return False

    # Whether it was playing at the previous reading, which is the
    # interval this is asking about.
    was, at, running = before
    # Where it should have reached: forward at real time while
    # playing, standing still otherwise.
    expected = was + (now - at) * 1000 if running else was

    return abs(position - expected) > SEEK_TOLERANCE * 1000


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    # Take ownership of runtime state before anything can read it.
    state.use_memory()
    log.info('carlib daemon starting; state held in memory')

    global _supervisor, _autostart_task, _geocoder, _audio_watch
    global _bluetooth_watch, _media_watch, _network_watch, _fm_watch

    _supervisor = asyncio.create_task(_run_supervisor())
    _autostart_task = asyncio.create_task(_autostart())
    _geocoder = asyncio.create_task(_watch_place())
    _audio_watch = asyncio.create_task(_watch_audio())
    _bluetooth_watch = asyncio.create_task(pairing.run())
    _media_watch = asyncio.create_task(_watch_media())
    _network_watch = asyncio.create_task(_watch_network())
    _fm_watch = asyncio.create_task(_watch_fm())

    _position_memory = asyncio.create_task(_remember_position())
    _position_watch = asyncio.create_task(_watch_position())

    # Navigation reports through the stream, and picks up a route left
    # unfinished when the car was turned off. Resumed here, before the
    # position watcher's first reading, so that reading can place it.
    session.current.on_change = lambda payload: events.events.publish(
        'navigation', payload)
    with contextlib.suppress(Exception):
        session.current.resume()

    # Map downloads report through the stream, so Settings > Map can
    # show progress -- and a screen opened halfway through picks it up
    # from the replay.
    download.on_change = lambda: events.events.publish(
        'map', download.status())

    # A download cut off by the daemon stopping -- the ignition going
    # off -- leaves its half-written file behind. Nothing is
    # downloading yet, so anything partial now is a leftover.
    for leftover in download.cleanup():
        log.info('map: removed leftover %s', leftover)

    yield

    await download.cancel()

    # Before the tasks. An open event stream never finishes on its
    # own, so uvicorn waits for it through the whole graceful
    # shutdown -- ending them first is what turns a stop that hangs
    # until systemd kills it into an immediate one.
    events.events.shutdown()

    _position_memory.cancel()
    _position_watch.cancel()

    for task in (_autostart_task, _geocoder, _audio_watch,
                 _bluetooth_watch, _media_watch, _network_watch,
                 _fm_watch, _supervisor):
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
    log.info('carlib daemon stopped')


app = FastAPI(title='carlib', lifespan=lifespan)

# Everything under one prefix so the frontend can proxy a single path
# in development, and so a UI route can never collide with an
# endpoint once the daemon serves the built assets from /.
API_PREFIX = '/api'

api = APIRouter(prefix=API_PREFIX)


@app.exception_handler(CarError)
async def handle_error(request: Request, exc: CarError) -> JSONResponse:
    """
    Turn library exceptions into the status codes the CLIs expect.

    Registered against CarError rather than Exception. A handler for
    Exception looks like it catches everything, but Starlette's
    ServerErrorMiddleware re-raises afterwards, so the traceback still
    reaches the log and uvicorn still reports an unhandled ASGI error
    -- for a perfectly ordinary 503.

    Every exception the library raises derives from CarError, so this
    covers them all. Anything else really is unexpected and should get
    Starlette's normal 500 handling, traceback included.
    """
    return JSONResponse(status_code=routes.status_for(exc),
                        content=routes.error_body(exc))


# --- Request bodies --------------------------------------------------------

class PlayBody(BaseModel):
    station: str | None = None
    # None means "use the setting" for both. Explicit values are for
    # the CLI's --gain and --no-rds, and last for that one tune.
    gain: float | None = None
    rds: bool | None = None


class TuneBody(BaseModel):
    offset: float


class SeekBody(BaseModel):
    direction: int = 1


class PresetBody(BaseModel):
    frequency: float
    name: str = ''


class ScanBody(BaseModel):
    threshold: float | None = None
    integration: int | None = None
    identify: bool = False
    resume: bool = True


class SelectBody(BaseModel):
    name: str


class SettingsBody(BaseModel):
    """
    Dotted keys to values, e.g. {"ui.theme": "night"}.

    Deliberately free-form: the catalogue documents what exists, but
    an undeclared key still works, and the API should not be the thing
    that stops it.
    """

    values: dict


class VolumeBody(BaseModel):
    percent: int


class PresetRef(BaseModel):
    frequency: float
    name: str = ''


class OrderBody(BaseModel):
    presets: list[PresetRef]


class SyncBody(BaseModel):
    address: str | None = None
    book: str = 'pb'
    photos: bool = False


class ModeBody(BaseModel):
    mode: str


class JoinBody(BaseModel):
    ssid: str
    # Absent for an open network, or one already saved -- the library
    # tries the saved profile first.
    password: str | None = None


class PositionBody(BaseModel):
    ms: int


class DefaultBody(BaseModel):
    node_id: int


class AdjustBody(BaseModel):
    delta: int


class MuteBody(BaseModel):
    """`muted` omitted means toggle."""

    muted: bool | None = None


class ServiceBody(BaseModel):
    active: bool


class WindowBody(BaseModel):
    seconds: int = 120


class AnswerBody(BaseModel):
    accept: bool


class Point(BaseModel):
    lat: float
    lon: float


class MapDownloadBody(BaseModel):
    # None means the last one chosen, from map.maxzoom.
    maxzoom: int | None = None


class RouteBody(BaseModel):
    points: list[Point]
    costing: str | None = None


class PlanBody(BaseModel):
    destination: Point
    stops: list[Point] = []


class Waypoint(BaseModel):
    latitude: float
    longitude: float
    title: str = ''
    subtitle: str = ''


class StartBody(BaseModel):
    choice: int = 0
    destination: Waypoint
    stops: list[Waypoint] = []


class UpdateBody(BaseModel):
    destination: Waypoint
    stops: list[Waypoint] = []


class PlaceBody(BaseModel):
    name: str
    latitude: float | None = None
    longitude: float | None = None
    altitude: float | None = None
    address: str = ''
    lookup: bool = True


# --- Routes ----------------------------------------------------------------

@api.get('/health')
async def get_health() -> dict:
    return await routes.health()


@api.get('/fm')
async def get_fm() -> dict:
    return await routes.fm_status()


@api.post('/fm/play')
async def post_fm_play(body: PlayBody | None = None) -> dict:
    body = body or PlayBody()
    return await routes.fm_play(body.station, body.gain, body.rds)


@api.post('/fm/restart')
async def post_fm_restart() -> dict:
    """Apply changed radio settings to a station already playing."""
    return await routes.fm_restart()


@api.post('/fm/pause')
async def post_fm_pause() -> dict:
    return await routes.fm_pause()


@api.post('/fm/toggle')
async def post_fm_toggle() -> dict:
    return await routes.fm_toggle()


@api.post('/fm/stop')
async def post_fm_stop() -> dict:
    return await routes.fm_stop()


@api.post('/fm/tune')
async def post_fm_tune(body: TuneBody) -> dict:
    return await routes.fm_tune(body.offset)


@api.post('/fm/seek')
async def post_fm_seek(body: SeekBody | None = None) -> dict:
    body = body or SeekBody()
    return await routes.fm_seek(body.direction)


@api.post('/fm/preset-step')
async def post_fm_preset_step(body: SeekBody | None = None) -> dict:
    body = body or SeekBody()
    return await routes.fm_next_preset(body.direction)


@api.get('/fm/rds')
async def get_fm_rds() -> dict:
    return await routes.fm_rds()


@api.get('/fm/presets')
async def get_fm_presets() -> list[dict]:
    return await routes.fm_presets()


@api.post('/fm/presets')
async def post_fm_preset(body: PresetBody) -> list[dict]:
    """Add or rename. Published, so every screen sees it -- the one
    that asked has the answer already."""
    stations = await routes.fm_add_preset(body.frequency, body.name)
    events.events.publish('presets', stations)
    return stations


@api.put('/fm/presets/order')
async def put_preset_order(body: OrderBody) -> list[dict]:
    """
    Put the presets in the order given.

    The whole list, not a move: a reorder is one intent, and applying
    it as a sequence of moves could leave a half-applied order behind
    if one failed.

    Registered before /fm/presets/{frequency}, or `order` would be
    read as a frequency.
    """
    frequencies = [s.frequency for s in body.presets]
    stations = await routes.fm_reorder_presets(frequencies)
    events.events.publish('presets', stations)
    return stations


@api.delete('/fm/presets/{frequency}')
async def delete_fm_preset(frequency: float) -> list[dict]:
    stations = await routes.fm_remove_preset(frequency)
    events.events.publish('presets', stations)
    return stations


@api.get('/fm/devices')
async def get_fm_devices() -> list[str]:
    return await routes.fm_devices()


@api.get('/fm/signals')
async def get_fm_signals() -> list[dict]:
    return await routes.fm_signals()


@api.post('/fm/scan')
async def post_fm_scan(body: ScanBody | None = None) -> list[dict]:
    """
    Sweep, and identify if asked. Answers when it has finished.

    Progress goes out as `scan` events while it runs, so a screen can
    show stations as they are found and named. The last one stays in
    the replay cache, which is how a screen opened mid-scan picks it
    up -- and why `signals` is published at the end too, for screens
    that only want the result.
    """
    body = body or ScanBody()
    signals = await routes.fm_scan(
        body.threshold, body.integration, body.identify, body.resume,
        report=lambda progress: events.events.publish(
            'scan', progress.to_dict()))
    events.events.publish('signals', signals)
    return signals


@api.get('/source')
async def get_source() -> dict:
    return await routes.source_status()


@api.post('/source/select')
async def post_source_select(body: SelectBody) -> dict:
    return await routes.source_select(body.name)


@api.post('/source/pause')
async def post_source_pause() -> dict:
    return await routes.source_pause()


@api.post('/source/toggle')
async def post_source_toggle() -> dict:
    return await routes.source_toggle()


@api.post('/source/ta-skip')
async def post_source_ta_skip() -> dict:
    return await routes.source_ta_skip()


# --- Location ---------------------------------------------------------------

@api.get('/geocode/suggest')
async def get_geocode_suggest(
        q: str,
        limit: int = 5,
        lat: float | None = None,
        lon: float | None = None,
        country: str | None = None,
        bias: bool | None = None) -> list[dict]:
    """
    Type-ahead suggestions.

    `bias` omitted follows the geocoding.bias setting; true or false
    overrides it for this request.
    """
    return await routes.geocode_suggest(q, limit, lat, lon, country,
                                        bias)


@api.get('/geocode/search')
async def get_geocode_search(
        q: str,
        limit: int = 5,
        country: str | None = None) -> list[dict]:
    return await routes.geocode_search(q, limit, country)


@api.get('/geocode/reverse')
async def get_geocode_reverse(lat: float, lon: float,
                              refresh: bool = False) -> dict:
    return await routes.geocode_reverse(lat, lon, refresh)


@api.get('/geocode/current')
async def get_geocode_current() -> dict | None:
    return await routes.geocode_current()


@api.get('/weather')
async def get_weather(place: str | None = None,
                      refresh: bool = False) -> dict:
    """
    The forecast for a saved place, or for where the car is when no
    place is named. Cached per location until the provider's Expires
    time; `refresh` asks again regardless.
    """
    return await routes.weather_forecast(place, refresh)


@api.get('/position')
async def get_position() -> dict:
    """
    Where the car is, and what that is based on: gps, last (no fix
    now, where it last had one), pin, or none. The same payload the
    'position' event carries, for a screen that cannot wait for it.
    """
    return await position.read()


@api.get('/places')
async def get_places() -> list[dict]:
    return await routes.places_list()


@api.get('/places/current')
async def get_places_current() -> dict | None:
    """
    Where we are, or null before the first fix.

    A convenience alias -- /places/current also resolves through the
    route below, which handles the reserved names itself. Declaring
    it here only changes whether an unknown position is null or a 404.
    """
    return await routes.places_current()


@api.get('/places/{name}')
async def get_place(name: str) -> dict:
    """
    One place by name.

    "current" and "here" resolve to where we are, so this does not
    depend on being declared after the literal route above.
    """
    return await routes.places_resolve(name)


@api.post('/places')
async def post_place(body: PlaceBody) -> list[dict]:
    return await routes.places_save(body.name, body.latitude,
                                    body.longitude, body.altitude,
                                    body.address, body.lookup)


@api.delete('/places/{name}')
async def delete_place(name: str) -> list[dict]:
    return await routes.places_remove(name)


# --- Settings ---------------------------------------------------------------

@api.get('/settings')
async def get_settings() -> dict:
    return await routes.settings_all()


@api.get('/settings/catalogue')
async def get_settings_catalogue() -> list[dict]:
    return await routes.settings_catalogue()


@api.put('/settings')
async def put_settings(body: SettingsBody) -> dict:
    return await routes.settings_update(body.values)


@api.delete('/settings/{key}')
async def delete_setting(key: str) -> dict:
    return await routes.settings_delete(key)


# --- Audio ------------------------------------------------------------------

@api.get('/audio')
async def get_audio() -> dict:
    """Volume, microphone and devices -- the same shape the stream
    publishes, so a screen can start from either."""
    return (await audio.state()).to_dict()


@api.post('/audio/volume')
async def post_audio_volume(body: VolumeBody) -> dict:
    return await routes.audio_set(body.percent)


@api.post('/audio/adjust')
async def post_audio_adjust(body: AdjustBody) -> dict:
    return await routes.audio_adjust(body.delta)


@api.post('/audio/mute')
async def post_audio_mute(body: MuteBody) -> dict:
    """`muted` omitted toggles, which is what a single button wants."""
    return await routes.audio_mute(body.muted)


@api.get('/audio/devices')
async def get_audio_devices() -> list[dict]:
    return await routes.audio_devices()


@api.post('/audio/default')
async def post_audio_default(body: DefaultBody) -> list[dict]:
    """Pin the default sink or source; wpctl remembers it."""
    return await routes.audio_set_default(body.node_id)


@api.post('/audio/devices/{node_id}/volume')
async def post_device_volume(node_id: int, body: VolumeBody) -> dict:
    return await routes.audio_device_volume(node_id, body.percent)


@api.post('/audio/devices/{node_id}/mute')
async def post_device_mute(node_id: int, body: MuteBody) -> dict:
    """`muted` omitted toggles."""
    return await routes.audio_device_mute(node_id, body.muted)


@api.post('/audio/streams/{node_id}/volume')
async def post_stream_volume(node_id: int, body: VolumeBody) -> dict:
    return await routes.audio_stream_volume(node_id, body.percent)


@api.post('/audio/streams/{node_id}/mute')
async def post_stream_mute(node_id: int, body: MuteBody) -> dict:
    return await routes.audio_stream_mute(node_id, bool(body.muted))


@api.get('/audio/microphone')
async def get_audio_microphone() -> dict:
    return await routes.audio_microphone()


@api.post('/audio/microphone')
async def post_audio_microphone(body: VolumeBody) -> dict:
    return await routes.audio_set_microphone(body.percent)


# --- Bluetooth --------------------------------------------------------------

@api.get('/bluetooth')
async def get_bluetooth() -> dict:
    """Adapter, devices, and whether a pairing window is open."""
    return await pairing.snapshot()


@api.post('/bluetooth/service')
async def post_bluetooth_service(body: ServiceBody) -> dict:
    return await routes.bluetooth_service(body.active)


@api.post('/bluetooth/pairing-mode')
async def post_pairing_mode(body: WindowBody) -> dict:
    """Scan, and be discoverable and pairable, for a while."""
    return await pairing.start(body.seconds)


@api.delete('/bluetooth/pairing-mode')
async def delete_pairing_mode() -> dict:
    return await pairing.stop()


@api.get('/bluetooth/pairing')
async def get_pairing_request() -> dict | None:
    """The pairing waiting for an answer, if there is one."""
    request = pairing.pending()
    return request.to_dict() if request else None


@api.post('/bluetooth/pairing')
async def post_pairing_answer(body: AnswerBody) -> dict:
    """
    Answer it.

    `answered` is false when there was nothing waiting -- BlueZ gives
    up after about thirty seconds, and an answer after that has
    nowhere to go.
    """
    return {'answered': pairing.answer(body.accept)}


@api.post('/bluetooth/devices/{address}/pair')
async def post_pair(address: str) -> dict:
    """Starts pairing and returns; progress arrives on the stream."""
    return pairing.pair(address)


@api.post('/bluetooth/devices/{address}/connect')
async def post_connect(address: str) -> dict:
    return await routes.bluetooth_connect(address)


@api.post('/bluetooth/devices/{address}/disconnect')
async def post_disconnect(address: str) -> dict:
    return await routes.bluetooth_disconnect(address)


@api.delete('/bluetooth/devices/{address}')
async def delete_device(address: str) -> dict:
    return await routes.bluetooth_forget(address)


# --- Media ------------------------------------------------------------------

@api.get('/media/{which}')
async def get_media(which: str) -> dict:
    """
    What a source is playing: bluetooth, spotify, or a player name.

    A source with nothing playing reports `present` false rather than
    failing -- a phone that has not started anything is the ordinary
    state, not an error.
    """
    return await routes.media_now(which)


@api.post('/media/{which}/position')
async def post_media_position(which: str, body: PositionBody) -> dict:
    """
    Move to a point in the track, in milliseconds.

    MPRIS only -- `seekable` on the reading says which sources take
    it. Registered before the action route, or `position` would be
    matched as an action name.
    """
    playing = await routes.media_seek(which, body.ms)
    events.events.publish('media', playing)
    return playing


@api.post('/media/{which}/{action}')
async def post_media(which: str, action: str) -> dict:
    """
    play, pause, stop, next, prev, forward or rewind.

    Returns once the player has caught up, and publishes the same
    reading -- so every screen settles together rather than the one
    that pressed the button being a poll ahead of the others.
    """
    playing = await routes.media_command(which, action)
    events.events.publish('media', playing)
    return playing


# --- Network ----------------------------------------------------------------

@api.get('/network')
async def get_network() -> dict:
    """Wi-Fi and hotspot together: one radio, one reading."""
    return await routes.network_status()


@api.post('/network/mode')
async def post_network_mode(body: ModeBody) -> dict:
    """wifi, hotspot or off. Takes a while -- services have to stop
    and start, and an association has to be made."""
    state = await routes.network_mode(body.mode)
    events.events.publish('network', state)
    return state


@api.get('/network/networks')
async def get_networks(rescan: bool = True) -> list[dict]:
    """What is in range. Takes a few seconds with rescan on."""
    return await routes.network_scan(rescan)


@api.post('/network/connect')
async def post_network_connect(body: JoinBody) -> dict:
    state = await routes.network_connect(body.ssid, body.password)
    events.events.publish('network', state)
    return state


@api.post('/network/disconnect')
async def post_network_disconnect() -> dict:
    state = await routes.network_disconnect()
    events.events.publish('network', state)
    return state


@api.delete('/network/networks/{ssid}')
async def delete_network(ssid: str) -> dict:
    state = await routes.network_forget(ssid)
    events.events.publish('network', state)
    return state


# --- Phonebook --------------------------------------------------------------

@api.get('/phonebook')
async def get_phonebook(address: str | None = None,
                        book: str = 'pb') -> dict:
    """
    The cached contacts for a phone, the connected one by default.

    Empty for a phone that has never been synced, which is the
    ordinary starting state rather than an error.
    """
    return await routes.phonebook_get(address, book)


@api.post('/phonebook/sync')
async def post_phonebook_sync(body: SyncBody) -> dict:
    """
    Pull from the phone. Slow -- every vCard over OBEX.

    `book` selects which: pb for contacts, ich/och/mch for the call
    logs, fav for favourites.

    `photos` asks for pictures as well, which multiplies the
    transfer -- a long book takes minutes rather than seconds.
    """
    return await routes.phonebook_sync(body.address, body.book,
                                       body.photos)


@api.get('/phonebook/photo/{digest}')
async def get_phonebook_photo(digest: str) -> FileResponse:
    """
    A contact's picture.

    Content addressed, so the name never changes for a given image
    and the browser can keep it -- a phonebook screen would otherwise
    re-fetch every avatar on every open.
    """
    return FileResponse(
        routes.phonebook_photo(digest),
        media_type='image/jpeg',
        headers={'Cache-Control': 'public, max-age=31536000, immutable'},
    )


@api.delete('/phonebook')
async def delete_phonebook(address: str | None = None,
                           book: str | None = None) -> dict:
    """One book, or every one of them when none is named."""
    return await routes.phonebook_forget(address, book)


# --- Events -----------------------------------------------------------------

@api.get('/events')
async def get_events() -> StreamingResponse:
    """
    The event stream.

    no-store and no-transform because a proxy that buffers this
    delivers nothing until it decides the response is finished, which
    for a stream is never.
    """
    return StreamingResponse(
        events.stream(),
        media_type='text/event-stream',
        headers={
            'Cache-Control': 'no-store, no-transform',
            'Connection': 'keep-alive',
            'X-Accel-Buffering': 'no',
        },
    )


# --- Navigation -------------------------------------------------------------

@api.post('/navigate/route')
async def post_navigate_route(body: RouteBody) -> dict:
    """A route through two or more points."""
    return await routes.navigate_route(
        [(p.lat, p.lon) for p in body.points], body.costing)


@api.post('/navigate/plan')
async def post_navigate_plan(body: PlanBody) -> dict:
    """
    A route from the car to the destination, through any stops, with
    up to two alternatives when there are none. Distances in metres,
    times in seconds, shapes as [lon, lat] for GeoJSON.

    Fails with 409 when the car's position is not known, 422 when no
    road leads there, 503 when the router cannot be reached.
    """
    return await routes.navigate_plan(
        (body.destination.lat, body.destination.lon),
        [(p.lat, p.lon) for p in body.stops])


@api.post('/navigate/start')
async def post_navigate_start(body: StartBody) -> dict:
    """Start following one of the last plan's routes."""
    return await routes.navigate_start(
        body.choice, body.destination.model_dump(),
        [s.model_dump() for s in body.stops])


@api.post('/navigate/update')
async def post_navigate_update(body: UpdateBody) -> dict:
    """A new destination or new stops while navigating."""
    return await routes.navigate_update(
        body.destination.model_dump(),
        [s.model_dump() for s in body.stops])


@api.post('/navigate/end')
async def post_navigate_end() -> dict:
    return await routes.navigate_end()


@api.get('/navigate/session')
async def get_navigate_session() -> dict:
    """The route being driven, its line included -- for a screen
    opening mid-drive, and once after every new route."""
    return await routes.navigate_session()


@api.post('/navigate/match')
async def post_navigate_match(body: RouteBody) -> dict:
    """Snap a GPS trace onto the road network."""
    return await routes.navigate_match(
        [(p.lat, p.lon) for p in body.points], body.costing)


@api.get('/map')
async def get_map() -> dict:
    """
    What is installed, the newest build if it has been looked up, and
    any download in progress. No network: see /map/latest.
    """
    return download.status()


@api.post('/map/latest')
async def post_map_latest() -> dict:
    """Look up the newest map build, then answer as GET /map."""
    await download.latest(refresh=True)
    status = download.status()
    events.events.publish('map', status)
    return status


@api.get('/map/estimate')
async def get_map_estimate(maxzoom: int) -> dict:
    """How big Sweden is at this detail level, in bytes."""
    return await download.estimate(maxzoom)


@api.post('/map/download')
async def post_map_download(body: MapDownloadBody | None = None) -> dict:
    """Start downloading the map. Progress arrives as `map` events."""
    download.start_tiles((body or MapDownloadBody()).maxzoom)
    return download.status()


@api.post('/map/labels/download')
async def post_map_labels_download() -> dict:
    """Start downloading label fonts and icons."""
    download.start_labels()
    return download.status()


@api.post('/map/cancel')
async def post_map_cancel() -> dict:
    return await download.cancel()


# Cached for a day rather than for ever: the names never change, but
# an update replaces the contents, and a day is soon enough to see it.
LABEL_CACHE = {'Cache-Control': 'public, max-age=86400'}


@api.get('/map/fonts/{stack}/{span}.pbf')
async def get_map_font(stack: str, span: str) -> FileResponse:
    """One glyph range, as MapLibre asks for them."""
    return FileResponse(tiles.font(stack, span),
                        media_type='application/x-protobuf',
                        headers=LABEL_CACHE)


@api.get('/map/sprites/{name}')
async def get_map_sprite(name: str) -> FileResponse:
    """An icon sheet (.png) or its index (.json)."""
    return FileResponse(tiles.sprite(name), headers=LABEL_CACHE)


@api.get('/map/tiles.pmtiles')
async def get_map_tiles() -> FileResponse:
    """
    The map archive, read by the browser in byte ranges.

    No long cache: the file is replaced when a new extract is made,
    and FileResponse's ETag lets the browser check cheaply.
    """
    return FileResponse(tiles.archive(),
                        media_type='application/octet-stream')


@api.get('/navigate/status')
async def get_navigate_status() -> dict:
    return await routes.navigate_status()


# Registered last, so every route above is on the router by now.
app.include_router(api)


# --- The screens ------------------------------------------------------------
#
# Registered after the router, so /api always wins: FastAPI tries
# routes in the order they were added, and the catch-all below would
# otherwise swallow every endpoint.


def _web_root() -> Path | None:
    """Where the built frontend is, if it is being served at all."""
    configured = settings.get('web.root', '')
    if not configured:
        return None

    root = Path(configured).expanduser()
    return root if root.is_dir() else None


@app.get('/{path:path}', include_in_schema=False)
async def screens(path: str) -> Response:
    """
    Serve the built frontend.

    Anything that is not a real file falls back to index.html, because
    the routes live in the browser: asking the daemon for
    /settings/sound directly has to return the app, which then reads
    the URL and shows that screen.
    """
    root = _web_root()
    if root is None:
        raise NotFoundError(
            'frontend', path,
            ['set web.root to the build directory, or use the dev '
             'server'])

    target = (root / path).resolve()

    # A path that climbs out of the root is not a typo; refuse rather
    # than explain.
    if root.resolve() not in target.parents and target != root.resolve():
        raise NotFoundError('file', path, [])

    if target.is_file():
        return FileResponse(target)

    index = root / 'index.html'
    if index.is_file():
        return FileResponse(index)

    raise NotFoundError('index.html', str(root), [])
