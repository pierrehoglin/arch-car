"""
Request handling, without the framework.

These are plain async functions returning plain dicts. FastAPI wiring
lives in main.py and does nothing but route to them, which keeps the
part that needs a web framework installed small enough to read in one
sitting -- and lets everything here be tested directly.
"""

from typing import Any

from carlib.core.errors import (
    CarError,
    NotFoundError,
    AmbiguousMatchError,
    NotAvailableError,
    TransferError,
)
from carlib.radio import fm
from carlib.system import source

# Library exceptions to HTTP status. Anything unmapped is a 500, which
# is correct: an unexpected exception is a bug here, not a client
# error.
STATUS = {
    NotFoundError: 404,
    AmbiguousMatchError: 409,
    NotAvailableError: 503,
    TransferError: 502,
}


def status_for(exc: Exception) -> int:
    """
    HTTP status for a library exception.

    Walks the class hierarchy so a subclass added later still maps
    sensibly rather than falling to 500.
    """
    for cls in type(exc).__mro__:
        if cls in STATUS:
            return STATUS[cls]
    if isinstance(exc, CarError):
        return 400
    return 500


def error_body(exc: Exception) -> dict:
    body: dict[str, Any] = {'error': str(exc),
                            'type': type(exc).__name__}
    hint = getattr(exc, 'hint', '')
    if hint:
        body['hint'] = hint
    return body


# --- FM --------------------------------------------------------------------

async def fm_status() -> dict:
    return (await fm.status()).to_dict()


async def fm_play(station: str | None = None,
                  gain: float | None = None,
                  rds: bool = True) -> dict:
    return (await fm.play(station, gain=gain, rds=rds)).to_dict()


async def fm_pause() -> dict:
    return (await fm.pause()).to_dict()


async def fm_toggle() -> dict:
    return (await fm.toggle()).to_dict()


async def fm_stop() -> dict:
    return (await fm.stop()).to_dict()


async def fm_tune(offset: float) -> dict:
    return (await fm.tune(offset)).to_dict()


async def fm_seek(direction: int = 1) -> dict:
    return (await fm.seek(direction)).to_dict()


async def fm_next_preset(step: int = 1) -> dict:
    return (await fm.next_preset(step)).to_dict()


async def fm_rds() -> dict:
    return (await fm.status()).rds.to_dict()


async def fm_presets() -> list[dict]:
    return [s.to_dict() for s in fm.load_presets()]


async def fm_add_preset(frequency: float, name: str = '') -> list[dict]:
    return [s.to_dict() for s in fm.add_preset(frequency, name)]


async def fm_remove_preset(frequency: float) -> list[dict]:
    return [s.to_dict() for s in fm.remove_preset(frequency)]


async def fm_scan(threshold: float | None = None,
                  integration: int | None = None,
                  identify: bool = False,
                  resume: bool = True) -> list[dict]:
    kwargs: dict[str, Any] = {'identify_stations': identify,
                              'resume': resume}
    if threshold is not None:
        kwargs['threshold'] = threshold
    if integration is not None:
        kwargs['integration'] = integration
    return [s.to_dict() for s in await fm.scan(**kwargs)]


async def fm_devices() -> list[str]:
    """
    RTL-SDR dongles visible to rtl_test.

    Goes through the daemon rather than being run locally: rtl_test
    opens the device, which would fail or interrupt playback if the
    daemon already has it.
    """
    return await fm.devices()


async def fm_signals() -> list[dict]:
    """Cached scan results, without sweeping."""
    signals, _ = fm.load_scan()
    return [s.to_dict() for s in signals]


# --- Sources ---------------------------------------------------------------

async def source_status() -> dict:
    return (await source.status()).to_dict()


async def source_select(name: str) -> dict:
    return (await source.select(name)).to_dict()


async def source_pause() -> dict:
    paused = await source.pause_others(keep='')
    return {'paused': paused}


async def source_toggle() -> dict:
    return (await source.toggle_play()).to_dict()


async def source_ta_skip() -> dict:
    return {'skipped': source.request_ta_skip()}


# --- Health ----------------------------------------------------------------

async def health() -> dict:
    """
    Enough for a client to tell the daemon is alive and sane.

    Deliberately does not touch hardware: a health check that hangs
    waiting for a USB device is worse than useless.
    """
    from carlib.core import state
    return {
        'ok': True,
        'state': 'memory' if state.in_memory() else 'files',
    }
