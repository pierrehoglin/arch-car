"""
Pairing, as the daemon runs it.

Everything here holds state between calls, which is why it lives in
the daemon and nowhere else: the agent has to stay registered to
answer BlueZ, a pairing window has to outlast the request that opened
it, and discovery stops the moment the D-Bus client that started it
goes away.

Pairing mode is one window with three things in it -- scanning,
discoverable and pairable -- opened together and closed together.
Outside it the car is invisible and accepts no new pairings, but
phones already paired still reconnect: those two properties only
govern new ones.
"""

import time
import json
import asyncio
import logging
from typing import Any, Callable

from carlib.bluetooth.agent import Agent, Request, register
from carlib.core.errors import CarError
from carlib.system import bluetooth

log = logging.getLogger('carlib')

DEFAULT_WINDOW = 120
MAX_WINDOW = 600

# How often state is read. Faster while pairing, when devices are
# appearing and a phone may be about to ask.
WATCH_INTERVAL = 2.0
WATCH_INTERVAL_PAIRING = 1.0

# BlueZ forgets agents when bluetoothd restarts, and there is no
# reliable signal that it has. Re-registering on a timer, and ignoring
# "already registered", covers it.
REREGISTER_EVERY = 10.0

Notify = Callable[[str, Any], None]


class Pairing:

    def __init__(self, notify: Notify) -> None:
        self._notify = notify
        self._agent = Agent(self._on_request)

        self._until: float | None = None
        self._closer: asyncio.Task | None = None
        self._attempts: dict[str, asyncio.Task] = {}
        self._attempt: dict | None = None

        self._last: str | None = None
        self._registered_at = 0.0

    # --- State -----------------------------------------------------------

    @property
    def open(self) -> bool:
        return self._until is not None and time.monotonic() < self._until

    def window(self) -> dict:
        if not self.open or self._until is None:
            return {'open': False, 'seconds_left': 0}
        left = max(0, round(self._until - time.monotonic()))
        return {'open': True, 'seconds_left': left}

    def pending(self) -> Request | None:
        return self._agent.pending

    async def snapshot(self) -> dict:
        """Everything a screen needs, in one reading."""
        adapter = await bluetooth.status()
        found = await bluetooth.devices() if adapter.service_active else []

        return {
            'adapter': adapter.to_dict(),
            'devices': [device.to_dict() for device in found],
            'window': self.window(),
            'attempt': self._attempt,
        }

    # --- The window ------------------------------------------------------

    async def start(self, seconds: int = DEFAULT_WINDOW) -> dict:
        """
        Open pairing mode, or extend it if it is already open.

        Clamped: a window left open indefinitely is a car anyone can
        pair with, which is the thing this exists to prevent.
        """
        seconds = max(10, min(MAX_WINDOW, int(seconds)))
        self._until = time.monotonic() + seconds

        try:
            await bluetooth.set_visible(True, seconds)
            await bluetooth.set_discovery(True)
        except CarError:
            # Half a window is worse than none: a car left discoverable
            # with nothing scheduled to close it. Roll back, then say.
            await self._shut()
            raise

        if self._closer is not None:
            self._closer.cancel()
        self._closer = asyncio.create_task(self._close_after(seconds))

        log.info('pairing: window open for %ds', seconds)
        await self._publish(force=True)
        return self.window()

    async def stop(self) -> dict:
        if self._closer is not None:
            self._closer.cancel()
            self._closer = None
        await self._shut()
        return self.window()

    async def _close_after(self, seconds: int) -> None:
        try:
            await asyncio.sleep(seconds)
        except asyncio.CancelledError:
            return
        self._closer = None
        await self._shut()

    async def _shut(self) -> None:
        self._until = None

        # Both, even if the first fails: a car left discoverable
        # because scanning would not stop is the worse failure.
        for step in (bluetooth.set_discovery(False),
                     bluetooth.set_visible(False)):
            try:
                await step
            except CarError as exc:
                log.warning('pairing: closing the window: %s', exc)

        log.info('pairing: window closed')
        await self._publish(force=True)

    # --- Pairing from the car's side -------------------------------------

    def pair(self, address: str) -> dict:
        """
        Start pairing with a device and return at once.

        Pairing waits for the code to be confirmed on both screens, so
        it runs as a task and reports on the stream. A request that
        waited for it would hold the connection open for half a minute.
        """
        key = address.upper()
        running = self._attempts.get(key)
        if running is not None and not running.done():
            return self._attempt or {}

        self._attempt = {'address': key, 'state': 'pairing', 'error': ''}
        self._attempts[key] = asyncio.create_task(self._pair(key))
        return self._attempt

    async def _pair(self, address: str) -> None:
        await self._publish(force=True)
        try:
            await bluetooth.pair(address)
            self._attempt = {'address': address, 'state': 'paired',
                             'error': ''}
        except CarError as exc:
            self._attempt = {'address': address, 'state': 'failed',
                             'error': str(exc).splitlines()[0]}
        finally:
            self._attempts.pop(address, None)
            await self._publish(force=True)

    # --- The agent's questions -------------------------------------------

    def answer(self, accept: bool) -> bool:
        return self._agent.answer(accept)

    def _on_request(self, request: Request | None) -> None:
        self._notify('pairing', request.to_dict() if request else None)

    # --- Watching --------------------------------------------------------

    async def _publish(self, force: bool = False) -> None:
        """Publish state, but only when it has changed."""
        try:
            state = await self.snapshot()
        except CarError:
            return

        encoded = json.dumps(state, sort_keys=True, default=str)
        if force or encoded != self._last:
            self._last = encoded
            self._notify('bluetooth', state)

    async def _tend(self) -> None:
        """One pass of upkeep."""
        adapter = await bluetooth.status()
        if not adapter.service_active:
            # Registration dies with bluetoothd. Forgetting when we
            # last did it means the next start re-registers at once.
            self._registered_at = 0.0
            return

        now = time.monotonic()
        if now - self._registered_at > REREGISTER_EVERY:
            await register(self._agent)
            self._registered_at = now

        # A phone that paired from its own side was confirmed through
        # the agent, and should reconnect on ignition without asking.
        for device in await bluetooth.devices():
            if device.paired and not device.trusted:
                try:
                    await bluetooth.trust(device.address)
                    log.info('pairing: trusted %s', device.name)
                except CarError as exc:
                    log.warning('pairing: trusting %s: %s', device.name, exc)

    async def run(self) -> None:
        """
        Keep the agent registered and the stream current, for ever.

        Errors are logged and retried rather than ending the loop:
        bluetoothd stops and starts, the adapter comes and goes, and
        none of that should take pairing down with it.
        """
        while True:
            try:
                await self._tend()
                await self._publish()
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception('bluetooth watch failed')

            await asyncio.sleep(
                WATCH_INTERVAL_PAIRING if self.open else WATCH_INTERVAL)
