"""
Request handling, without the framework.

These are plain async functions returning plain dicts. FastAPI wiring
lives in main.py and does nothing but route to them, which keeps the
part that needs a web framework installed small enough to read in one
sitting -- and lets everything here be tested directly.
"""

from typing import Any

from carlib.core import settings
from carlib.core.errors import (
    CarError,
    NotFoundError,
    AmbiguousMatchError,
    NotAvailableError,
    TransferError,
)
from carlib.location import geocoding, places
from carlib.navigation import routing
from carlib.radio import fm
from carlib.system import audio, bluetooth, pipewire, source

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


# --- Location ---------------------------------------------------------------

async def geocode_suggest(query: str, limit: int = 5,
                          latitude: float | None = None,
                          longitude: float | None = None,
                          country: str | None = None,
                          bias: bool | None = None) -> list[dict]:
    rows = await geocoding.suggest(query, limit=limit,
                                   latitude=latitude,
                                   longitude=longitude,
                                   country=country,
                                   bias=bias)
    return [r.to_dict() for r in rows]


async def geocode_search(query: str, limit: int = 5,
                         country: str | None = None) -> list[dict]:
    rows = await geocoding.search(query, limit=limit, country=country)
    return [r.to_dict() for r in rows]


async def geocode_reverse(latitude: float, longitude: float,
                          refresh: bool = False) -> dict:
    address = await geocoding.reverse(latitude, longitude,
                                      use_cache=not refresh)
    return address.to_dict()


async def geocode_current() -> dict | None:
    """
    Our own address, from the cache.

    Never queries, so a UI can poll it as often as it likes.
    """
    address = geocoding.current()
    return address.to_dict() if address else None


async def places_list() -> list[dict]:
    return [p.to_dict() for p in places.saved()]


async def places_current() -> dict | None:
    place = places.current()
    return place.to_dict() if place else None


async def places_save(name: str, latitude: float | None = None,
                      longitude: float | None = None,
                      altitude: float | None = None,
                      address: str = '',
                      lookup: bool = True) -> list[dict]:
    if latitude is None or longitude is None:
        here = await places.here()
        latitude, longitude = here.latitude, here.longitude
        altitude = here.altitude if altitude is None else altitude

    rows = await places.save(name, latitude, longitude, altitude,
                             address=address, lookup=lookup)
    return [p.to_dict() for p in rows]


async def places_remove(name: str) -> list[dict]:
    return [p.to_dict() for p in places.remove(name)]


async def places_resolve(name: str | None = None) -> dict:
    return (await places.resolve(name)).to_dict()


async def navigate_route(points: list[tuple[float, float]],
                         costing: str | None = None) -> dict:
    result = await routing.route(points, costing=costing)
    return result.to_dict()


async def navigate_match(points: list[tuple[float, float]],
                         costing: str | None = None) -> dict:
    result = await routing.match(points, costing=costing)
    return result.to_dict()


async def navigate_status() -> dict:
    return await routing.status()


# --- Audio ------------------------------------------------------------------

async def audio_set(percent: int) -> dict:
    """
    Set the volume as a percentage.

    The module clamps to 100 rather than letting wpctl run past it
    into distortion, so a caller cannot ask for more than the
    hardware should be given.
    """
    return (await audio.set_volume(percent)).to_dict()


async def audio_adjust(delta: int) -> dict:
    return (await audio.adjust(delta)).to_dict()


async def audio_mute(muted: bool | None = None) -> dict:
    """Mute, unmute, or -- with nothing given -- toggle."""
    if muted is None:
        return (await audio.toggle_mute()).to_dict()
    return (await audio.set_muted(muted)).to_dict()


async def audio_devices() -> list[dict]:
    """Every sink and source, with the default of each marked."""
    return [device.to_dict() for device in await audio.devices()]


async def audio_set_default(node_id: int) -> list[dict]:
    """
    Choose the default sink or source.

    wpctl writes the choice to WirePlumber's own state, so it holds
    across restarts. Without ever setting one, WirePlumber picks by
    priority at every boot -- which means the output moves depending
    on what happens to be plugged in.
    """
    return [device.to_dict() for device in await audio.set_default(node_id)]


async def audio_device_volume(node_id: int, percent: int) -> dict:
    """
    Set one device's level, rather than whichever is default.

    wpctl takes a node id wherever it takes @DEFAULT_AUDIO_SINK@, so
    this is the same call with a different target.
    """
    return (await audio.set_volume(percent, str(node_id))).to_dict()


async def audio_device_mute(node_id: int, muted: bool | None) -> dict:
    if muted is None:
        return (await audio.toggle_mute(str(node_id))).to_dict()
    return (await audio.set_muted(muted, str(node_id))).to_dict()


async def audio_stream_volume(node_id: int, percent: int) -> dict:
    """
    Level one application against the others.

    WirePlumber remembers these by application name, so setting FM
    down once holds across restarts -- which is the point. Levelling
    that had to be redone every boot would not be worth having.
    """
    if not await pipewire.exists(node_id):
        raise NotFoundError('stream', str(node_id), [])

    await pipewire.set_volume(node_id, percent)
    level, muted = await pipewire.get_volume(node_id)
    return {'node_id': node_id, 'percent': level, 'muted': muted}


async def audio_stream_mute(node_id: int, muted: bool) -> dict:
    if not await pipewire.exists(node_id):
        raise NotFoundError('stream', str(node_id), [])

    await pipewire.set_mute(node_id, muted)
    level, is_muted = await pipewire.get_volume(node_id)
    return {'node_id': node_id, 'percent': level, 'muted': is_muted}


async def audio_microphone() -> dict:
    return (await audio.microphone()).to_dict()


async def audio_set_microphone(percent: int) -> dict:
    return (await audio.set_microphone(percent)).to_dict()


# --- Bluetooth --------------------------------------------------------------
#
# Pairing state lives in the daemon (carlib.bluetooth.pairing), so the
# routes that need it are given it by main.py rather than importing a
# module-level instance -- the CLI imports this module too, and must
# not start an agent by doing so.

async def bluetooth_service(active: bool) -> dict:
    """On and off is the service, not the radio."""
    state = await (bluetooth.service_start() if active
                   else bluetooth.service_stop())
    return state.to_dict()


async def bluetooth_forget(address: str) -> dict:
    await bluetooth.forget(address)
    return {'forgotten': address.upper()}


async def bluetooth_connect(address: str) -> dict:
    return (await bluetooth.connect(address)).to_dict()


async def bluetooth_disconnect(address: str) -> dict:
    return (await bluetooth.disconnect(address)).to_dict()


# --- Media ------------------------------------------------------------------
#
# One shape for both transports. AVRCP and MPRIS carry the same things
# under different names, so the screens differ only in which source
# they read.

async def media_now(which: str) -> dict:
    return (await source.now_playing(which)).to_dict()


async def media_seek(which: str, ms: int) -> dict:
    return (await source.seek(which, ms)).to_dict()


async def media_command(which: str, action: str) -> dict:
    if action not in source.ACTIONS:
        raise NotFoundError('action', action, list(source.ACTIONS))
    return (await source.command(which, action)).to_dict()


# --- Settings ---------------------------------------------------------------

async def settings_all() -> dict:
    """Everything that has been set, as a nested object."""
    return settings.reload()


async def settings_catalogue() -> list[dict]:
    """
    Every setting that exists, whether or not it has been set.

    What a settings screen needs: the key, its type, what it defaults
    to, and a line describing it -- so the UI does not have to carry
    its own copy of any of that.
    """
    sentinel = object()
    rows = []

    for entry in settings.catalogue():
        value = settings.get(entry.key, sentinel)
        rows.append({
            'key': entry.key,
            'kind': entry.kind,
            'default': entry.default,
            'description': entry.description,
            'value': None if value is sentinel else value,
            'set': value is not sentinel,
        })

    return rows


async def settings_update(values: dict) -> dict:
    """
    Set several keys at once.

    One write for the whole change, so a screen toggling two things
    together cannot leave half of it on disk.
    """
    if values:
        settings.update(values)
    return settings.reload()


async def settings_delete(key: str) -> dict:
    """Remove a key, returning it to its default."""
    settings.delete(key)
    return settings.reload()


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
