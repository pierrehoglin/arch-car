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

from carlib.core import state
from carlib.core.errors import CarError
from carlib.api import routes
from carlib.system import source

log = logging.getLogger('carlib')

_supervisor: asyncio.Task | None = None


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


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    # Take ownership of runtime state before anything can read it.
    state.use_memory()
    log.info('carlib daemon starting; state held in memory')

    global _supervisor
    _supervisor = asyncio.create_task(_run_supervisor())

    yield

    if _supervisor is not None:
        _supervisor.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await _supervisor
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
