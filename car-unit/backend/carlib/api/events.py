"""
The event stream.

One connection carrying named events, so a screen hears about a
change when it happens rather than on its next poll. Commands stay
POSTs; this is the direction that needed a channel.

Server-sent events rather than a WebSocket: everything here goes one
way, it is plain HTTP on the same port, and EventSource reconnects by
itself. That last point costs nothing in the car, where the daemon
runs until the ignition goes off, but it saves writing reconnection
logic for development.
"""

import json
import asyncio
import logging
from typing import Any, AsyncIterator

log = logging.getLogger('carlib')

# Dropped rather than queued past this. A client that cannot keep up
# with a volume knob is not going to catch up, and holding events for
# it would grow without limit.
QUEUE_LIMIT = 64

# A comment line the client ignores. Without traffic a proxy is
# entitled to drop an idle connection, and the first anyone would know
# is a screen quietly going stale.
HEARTBEAT = 15.0


class Events:
    """
    Fan-out to every connected client.

    Each subscriber gets its own queue, so a slow one cannot hold up
    the others -- it loses events instead, which for state that is
    resent on the next change is the better failure.
    """

    def __init__(self) -> None:
        self._clients: set[asyncio.Queue] = set()
        # The last of each kind, so a client connecting mid-session is
        # populated without also having to fetch.
        self._latest: dict[str, Any] = {}

    def publish(self, event: str, data: Any) -> None:
        self._latest[event] = data

        for queue in list(self._clients):
            try:
                queue.put_nowait((event, data))
            except asyncio.QueueFull:
                log.debug('event client is behind; dropping %s', event)

    def subscribe(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=QUEUE_LIMIT)

        for event, data in self._latest.items():
            queue.put_nowait((event, data))

        self._clients.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        self._clients.discard(queue)

    @property
    def clients(self) -> int:
        return len(self._clients)


events = Events()


def frame(event: str, data: Any) -> str:
    """One SSE frame. The blank line is what ends it."""
    return f'event: {event}\ndata: {json.dumps(data)}\n\n'


async def stream() -> AsyncIterator[str]:
    """
    A client's view of the feed.

    Ends when the client goes away: the generator is closed, which
    raises GeneratorExit at the yield and runs the finally.
    """
    queue = events.subscribe()

    try:
        while True:
            try:
                event, data = await asyncio.wait_for(
                    queue.get(), timeout=HEARTBEAT)
            except asyncio.TimeoutError:
                yield ': keep-alive\n\n'
                continue

            yield frame(event, data)
    finally:
        events.unsubscribe(queue)
