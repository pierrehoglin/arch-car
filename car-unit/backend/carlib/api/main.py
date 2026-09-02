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

import asyncio
import logging
import contextlib

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from carlib.core import settings, state
from carlib.core.errors import CarError
from carlib.api import routes
from carlib.location import geocoding
from carlib.radio import fm
from carlib.system import source

log = logging.getLogger('carlib')

_supervisor: asyncio.Task | None = None
_autostart_task: asyncio.Task | None = None
_geocoder: asyncio.Task | None = None


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


async def _run_geocoder() -> None:
    """
    Keep the current address up to date as the car moves.

    Here rather than in its own service because Nominatim's rate
    limit applies across the whole application: two processes would
    each keep their own limiter and could exceed it between them.

    Off by default. It is a third-party service with a usage policy
    attached, so it should be a deliberate choice:

        settings set geocoding.auto true
    """
    while True:
        if not settings.get_bool('geocoding.auto', False):
            await asyncio.sleep(60)
            continue

        try:
            async for address in geocoding.watch():
                log.info('location: %s', address.short)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception('geocoder failed; restarting in 60s')
            await asyncio.sleep(60)


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    # Take ownership of runtime state before anything can read it.
    state.use_memory()
    log.info('carlib daemon starting; state held in memory')

    global _supervisor, _autostart_task, _geocoder
    _supervisor = asyncio.create_task(_run_supervisor())
    _autostart_task = asyncio.create_task(_autostart())
    _geocoder = asyncio.create_task(_run_geocoder())

    yield

    for task in (_autostart_task, _geocoder, _supervisor):
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
    log.info('carlib daemon stopped')


app = FastAPI(title='carlib', lifespan=lifespan)


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
    gain: float | None = None
    rds: bool = True


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


class PlaceBody(BaseModel):
    name: str
    latitude: float | None = None
    longitude: float | None = None
    altitude: float | None = None
    address: str = ''
    lookup: bool = True


# --- Routes ----------------------------------------------------------------

@app.get('/health')
async def get_health() -> dict:
    return await routes.health()


@app.get('/fm')
async def get_fm() -> dict:
    return await routes.fm_status()


@app.post('/fm/play')
async def post_fm_play(body: PlayBody | None = None) -> dict:
    body = body or PlayBody()
    return await routes.fm_play(body.station, body.gain, body.rds)


@app.post('/fm/pause')
async def post_fm_pause() -> dict:
    return await routes.fm_pause()


@app.post('/fm/toggle')
async def post_fm_toggle() -> dict:
    return await routes.fm_toggle()


@app.post('/fm/stop')
async def post_fm_stop() -> dict:
    return await routes.fm_stop()


@app.post('/fm/tune')
async def post_fm_tune(body: TuneBody) -> dict:
    return await routes.fm_tune(body.offset)


@app.post('/fm/seek')
async def post_fm_seek(body: SeekBody | None = None) -> dict:
    body = body or SeekBody()
    return await routes.fm_seek(body.direction)


@app.post('/fm/preset-step')
async def post_fm_preset_step(body: SeekBody | None = None) -> dict:
    body = body or SeekBody()
    return await routes.fm_next_preset(body.direction)


@app.get('/fm/rds')
async def get_fm_rds() -> dict:
    return await routes.fm_rds()


@app.get('/fm/presets')
async def get_fm_presets() -> list[dict]:
    return await routes.fm_presets()


@app.post('/fm/presets')
async def post_fm_preset(body: PresetBody) -> list[dict]:
    return await routes.fm_add_preset(body.frequency, body.name)


@app.delete('/fm/presets/{frequency}')
async def delete_fm_preset(frequency: float) -> list[dict]:
    return await routes.fm_remove_preset(frequency)


@app.get('/fm/devices')
async def get_fm_devices() -> list[str]:
    return await routes.fm_devices()


@app.get('/fm/signals')
async def get_fm_signals() -> list[dict]:
    return await routes.fm_signals()


@app.post('/fm/scan')
async def post_fm_scan(body: ScanBody | None = None) -> list[dict]:
    body = body or ScanBody()
    return await routes.fm_scan(body.threshold, body.integration,
                                body.identify, body.resume)


@app.get('/source')
async def get_source() -> dict:
    return await routes.source_status()


@app.post('/source/select')
async def post_source_select(body: SelectBody) -> dict:
    return await routes.source_select(body.name)


@app.post('/source/pause')
async def post_source_pause() -> dict:
    return await routes.source_pause()


@app.post('/source/toggle')
async def post_source_toggle() -> dict:
    return await routes.source_toggle()


@app.post('/source/ta-skip')
async def post_source_ta_skip() -> dict:
    return await routes.source_ta_skip()


# --- Location ---------------------------------------------------------------

@app.get('/geocode/suggest')
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


@app.get('/geocode/search')
async def get_geocode_search(
        q: str,
        limit: int = 5,
        country: str | None = None) -> list[dict]:
    return await routes.geocode_search(q, limit, country)


@app.get('/geocode/reverse')
async def get_geocode_reverse(lat: float, lon: float,
                              refresh: bool = False) -> dict:
    return await routes.geocode_reverse(lat, lon, refresh)


@app.get('/geocode/current')
async def get_geocode_current() -> dict | None:
    return await routes.geocode_current()


@app.get('/places')
async def get_places() -> list[dict]:
    return await routes.places_list()


@app.get('/places/current')
async def get_places_current() -> dict | None:
    """
    Where we are, or null before the first fix.

    A convenience alias -- /places/current also resolves through the
    route below, which handles the reserved names itself. Declaring
    it here only changes whether an unknown position is null or a 404.
    """
    return await routes.places_current()


@app.get('/places/{name}')
async def get_place(name: str) -> dict:
    """
    One place by name.

    "current" and "here" resolve to where we are, so this does not
    depend on being declared after the literal route above.
    """
    return await routes.places_resolve(name)


@app.post('/places')
async def post_place(body: PlaceBody) -> list[dict]:
    return await routes.places_save(body.name, body.latitude,
                                    body.longitude, body.altitude,
                                    body.address, body.lookup)


@app.delete('/places/{name}')
async def delete_place(name: str) -> list[dict]:
    return await routes.places_remove(name)
