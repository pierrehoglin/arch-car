"""
Client for the carlib daemon.

Exposes `fm` and `source` objects with the same method names and
return types as the library modules, so a CLI changes one import line
rather than every call site:

    from carlib.radio import fm          # direct
    from carlib.api.client import fm     # via the daemon

Responses are rebuilt into the same dataclasses, so display code works
either way.

When the daemon is not running this raises NotAvailableError telling
you to start it, rather than falling back to calling the library
directly. A silent fallback would mean two processes owning runtime
state again -- the exact problem the daemon exists to solve -- and the
failure would show up later as something inexplicable.
"""

import os
import json
from pathlib import Path
from typing import Any

from carlib.core.errors import (
    CarError,
    NotFoundError,
    AmbiguousMatchError,
    NotAvailableError,
    TransferError,
)
from carlib.api.serialise import from_dict
from carlib.radio.fm import (
    RadioState, Rds, Signal, Station,
    parse_frequency,
    DEFAULT_GAIN, SCAN_THRESHOLD_DB, SCAN_INTEGRATION,
)
from carlib.system.source import (
    SourceState, POLL_INTERVAL, TA_POLL_INTERVAL, FM,
)
from carlib.location.geocoding import Address
from carlib.location.places import Place, CURRENT

# Any host is accepted for a Unix socket; httpx requires one.
BASE_URL = 'http://carlib'

TIMEOUT = 30.0

# Scanning tunes across the whole band and may identify each station,
# which takes far longer than a normal request.
SCAN_TIMEOUT = 300.0

# Reverse of routes.STATUS.
EXCEPTIONS = {
    404: NotFoundError,
    409: AmbiguousMatchError,
    502: TransferError,
    503: NotAvailableError,
}


def socket_path() -> Path:
    base = os.environ.get('XDG_RUNTIME_DIR')
    return Path(base or '/tmp') / 'carlib.sock'


def _raise_for(status: int, body: Any) -> None:
    """Turn an error response back into the original exception type."""
    message = 'request failed'
    hint = ''

    if isinstance(body, dict):
        message = body.get('error') or message
        hint = body.get('hint', '')

    cls = EXCEPTIONS.get(status, CarError)

    # The typed constructors take structured arguments the wire format
    # does not preserve, so raise the base class with the server's
    # message rather than trying to reconstruct them.
    if cls in (NotFoundError, AmbiguousMatchError):
        raise CarError(message) from None
    if cls is NotAvailableError:
        raise NotAvailableError(message, hint=hint) from None
    if cls is TransferError:
        raise TransferError(message) from None
    raise CarError(message) from None


async def request(method: str, path: str,
                  body: dict | None = None,
                  timeout: float = TIMEOUT,
                  query: dict | None = None) -> Any:
    """
    One request to the daemon over its Unix socket.

    httpx is imported here rather than at module scope so the CLIs
    still start -- and can report a useful error -- on a machine where
    the API extra was never installed.
    """
    # Socket first: "the service is not running" is the far more
    # common cause, and reporting a missing dependency instead would
    # send you looking in the wrong place.
    sock = socket_path()
    if not sock.exists():
        raise NotAvailableError(
            'carlib service is not running',
            hint='systemctl --user start carlib')

    try:
        import httpx
    except ImportError as exc:
        raise NotAvailableError(
            'httpx is not installed',
            hint='uv sync --extra api') from exc

    transport = httpx.AsyncHTTPTransport(uds=str(sock))

    try:
        async with httpx.AsyncClient(transport=transport,
                                     base_url=BASE_URL,
                                     timeout=timeout) as client:
            response = await client.request(method, path, json=body,
                                            params=query)
    except Exception as exc:
        if isinstance(exc, CarError):
            raise
        raise NotAvailableError(
            f'cannot reach the carlib service: {exc}',
            hint='systemctl --user status carlib') from exc

    if response.status_code >= 400:
        try:
            payload = response.json()
        except json.JSONDecodeError:
            payload = {'error': response.text}
        _raise_for(response.status_code, payload)

    if not response.content:
        return None
    return response.json()


async def health() -> dict:
    return await request('GET', '/health')


async def available() -> bool:
    """Whether the daemon is reachable. Never raises."""
    try:
        await health()
        return True
    except CarError:
        return False


class _Fm:
    """
    Mirrors carlib.radio.fm over HTTP.

    Constants and pure functions are re-exported as attributes so a
    caller can swap `from carlib.radio import fm` for
    `from carlib.api.client import fm` and nothing else changes.
    """

    # Constants: values, not state, so reading them locally is right.
    DEFAULT_GAIN = DEFAULT_GAIN
    SCAN_THRESHOLD_DB = SCAN_THRESHOLD_DB
    SCAN_INTEGRATION = SCAN_INTEGRATION

    # Pure function -- parsing a frequency needs no daemon.
    parse_frequency = staticmethod(parse_frequency)

    async def status(self) -> RadioState:
        return from_dict(RadioState, await request('GET', '/fm'))

    async def play(self, station=None, gain=None, rds=True,
                   **_ignored) -> RadioState:
        body = {'station': None if station is None else str(station),
                'gain': gain, 'rds': rds}
        return from_dict(RadioState,
                         await request('POST', '/fm/play', body))

    async def pause(self) -> RadioState:
        return from_dict(RadioState, await request('POST', '/fm/pause'))

    async def toggle(self) -> RadioState:
        return from_dict(RadioState, await request('POST', '/fm/toggle'))

    async def stop(self) -> RadioState:
        return from_dict(RadioState, await request('POST', '/fm/stop'))

    async def tune(self, offset: float) -> RadioState:
        return from_dict(RadioState, await request(
            'POST', '/fm/tune', {'offset': offset}))

    async def seek(self, direction: int = 1, **_ignored) -> RadioState:
        return from_dict(RadioState, await request(
            'POST', '/fm/seek', {'direction': direction}))

    async def next_preset(self, step: int = 1) -> RadioState:
        return from_dict(RadioState, await request(
            'POST', '/fm/preset-step', {'direction': step}))

    async def scan(self, identify_stations: bool = False,
                   resume: bool = True, threshold=None,
                   integration=None, **_ignored) -> list[Signal]:
        body = {'threshold': threshold, 'integration': integration,
                'identify': identify_stations, 'resume': resume}
        rows = await request('POST', '/fm/scan', body,
                             timeout=SCAN_TIMEOUT)
        return [from_dict(Signal, r) for r in rows]

    async def devices(self) -> list[str]:
        return await request('GET', '/fm/devices')

    async def signals(self) -> list[Signal]:
        rows = await request('GET', '/fm/signals')
        return [from_dict(Signal, r) for r in rows]

    async def rds(self) -> Rds:
        return from_dict(Rds, await request('GET', '/fm/rds'))

    # Presets live in settings, which is a shared file rather than
    # runtime state, so these could read locally -- but going through
    # the daemon keeps one writer and avoids a lost update when the UI
    # and a CLI both save at once.

    async def load_presets(self) -> list[Station]:
        rows = await request('GET', '/fm/presets')
        return [from_dict(Station, r) for r in rows]

    async def add_preset(self, frequency: float,
                         name: str = '') -> list[Station]:
        rows = await request('POST', '/fm/presets',
                             {'frequency': frequency, 'name': name})
        return [from_dict(Station, r) for r in rows]

    async def remove_preset(self, frequency: float) -> list[Station]:
        rows = await request('DELETE', f'/fm/presets/{frequency}')
        return [from_dict(Station, r) for r in rows]


class _Source:
    """Mirrors carlib.system.source over HTTP."""

    POLL_INTERVAL = POLL_INTERVAL
    TA_POLL_INTERVAL = TA_POLL_INTERVAL
    FM = FM

    async def status(self) -> SourceState:
        return from_dict(SourceState, await request('GET', '/source'))

    async def select(self, name: str, **_ignored) -> SourceState:
        return from_dict(SourceState, await request(
            'POST', '/source/select', {'name': name}))

    async def pause_others(self, keep: str = '') -> list[str]:
        result = await request('POST', '/source/pause')
        return result.get('paused', [])

    async def toggle_play(self) -> SourceState:
        return from_dict(SourceState,
                         await request('POST', '/source/toggle'))

    async def request_ta_skip(self) -> bool:
        result = await request('POST', '/source/ta-skip')
        return bool(result.get('skipped', False))


class _Geocoding:
    """Mirrors carlib.location.geocoding over HTTP."""

    CURRENT = CURRENT

    async def suggest(self, query: str, limit: int = 5,
                      latitude: float | None = None,
                      longitude: float | None = None,
                      country: str | None = None,
                      bias: bool | None = None,
                      **_ignored) -> list[Address]:
        params: dict = {'q': query, 'limit': limit}
        if latitude is not None:
            params['lat'] = latitude
        if longitude is not None:
            params['lon'] = longitude
        if country is not None:
            params['country'] = country
        if bias is not None:
            params['bias'] = bias
        rows = await request('GET', '/geocode/suggest', query=params)
        return [from_dict(Address, r) for r in rows]

    async def search(self, query: str, limit: int = 5,
                     country: str | None = None,
                     **_ignored) -> list[Address]:
        params: dict = {'q': query, 'limit': limit}
        if country is not None:
            params['country'] = country
        rows = await request('GET', '/geocode/search', query=params)
        return [from_dict(Address, r) for r in rows]

    async def reverse(self, latitude: float, longitude: float,
                      use_cache: bool = True, **_ignored) -> Address:
        row = await request('GET', '/geocode/reverse',
                            query={'lat': latitude, 'lon': longitude,
                                   'refresh': not use_cache})
        return from_dict(Address, row)

    async def current(self) -> Address | None:
        row = await request('GET', '/geocode/current')
        return from_dict(Address, row) if row else None


class _Places:
    """Mirrors carlib.location.places over HTTP."""

    CURRENT = CURRENT

    async def saved(self) -> list[Place]:
        rows = await request('GET', '/places')
        return [from_dict(Place, r) for r in rows]

    async def current(self) -> Place | None:
        row = await request('GET', '/places/current')
        return from_dict(Place, row) if row else None

    async def resolve(self, name: str | None = None) -> Place:
        row = await request('GET', f'/places/{name or CURRENT}')
        return from_dict(Place, row)

    async def here(self) -> Place:
        return await self.resolve(CURRENT)

    async def save(self, name: str, latitude: float | None = None,
                   longitude: float | None = None,
                   altitude: float | None = None,
                   address: str = '', lookup: bool = True,
                   **_ignored) -> list[Place]:
        rows = await request('POST', '/places', {
            'name': name, 'latitude': latitude,
            'longitude': longitude, 'altitude': altitude,
            'address': address, 'lookup': lookup,
        })
        return [from_dict(Place, r) for r in rows]

    async def remove(self, name: str) -> list[Place]:
        rows = await request('DELETE', f'/places/{name}')
        return [from_dict(Place, r) for r in rows]


fm = _Fm()
source = _Source()
geocoding = _Geocoding()
places = _Places()
