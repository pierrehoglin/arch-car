"""
PipeWire node lookup and per-stream volume.

Muting one stream needs its node id, and PipeWire assigns those
sequentially at runtime: they change on every restart, differ between
machines, and a fresh one is issued each time a stream is created.
There is nothing stable to hard-code.

What is stable is the id for the lifetime of a stream. So the pattern
is resolve once when the stream starts, cache it, and re-resolve only
when an operation fails -- which is what a stale id looks like.

Streams are found by their PipeWire properties rather than by name.
Tag a stream at launch and it can be found again:

    PULSE_PROP='application.name=carlib-fm' play ...

Requires pipewire-pulse and wireplumber, both already needed for
audio.
"""

import json
import asyncio
from dataclasses import dataclass, asdict

from carlib.core.errors import NotAvailableError, NotFoundError

PW_DUMP = 'pw-dump'
WPCTL = 'wpctl'

# Playback streams. Sinks and sources have different media classes.
STREAM_OUTPUT = 'Stream/Output/Audio'


@dataclass
class Node:
    id: int
    name: str = ''
    application: str = ''
    media_class: str = ''
    state: str = ''
    binary: str = ''

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def running(self) -> bool:
        return self.state == 'running'


async def _run(*args: str, timeout: float = 5.0) -> str:
    try:
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError as exc:
        raise NotAvailableError(
            f'{args[0]} not found',
            hint='pacman -S pipewire wireplumber') from exc

    try:
        out, err = await asyncio.wait_for(proc.communicate(),
                                          timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        raise NotAvailableError(f'timed out: {" ".join(args)}')

    if proc.returncode != 0:
        message = err.decode(errors='replace').strip() or 'unknown error'
        raise NotAvailableError(
            f'{args[0]} failed: {message}',
            hint='is PipeWire running in this session? A system '
                 'service needs XDG_RUNTIME_DIR set.')

    return out.decode(errors='replace')


def parse_nodes(text: str) -> list[Node]:
    """
    Pull audio nodes out of `pw-dump` output.

    pw-dump emits every object on the graph -- nodes, ports, links,
    devices, factories. Only Node objects with a media class matter
    here, and properties are nested under info.props.
    """
    try:
        objects = json.loads(text)
    except json.JSONDecodeError:
        return []

    if not isinstance(objects, list):
        return []

    nodes = []
    for entry in objects:
        if not isinstance(entry, dict):
            continue
        if entry.get('type') != 'PipeWire:Interface:Node':
            continue

        info = entry.get('info') or {}
        props = info.get('props') or {}

        media_class = props.get('media.class', '')
        if not media_class:
            continue

        nodes.append(Node(
            id=int(entry.get('id', 0)),
            name=props.get('node.name', ''),
            application=props.get('application.name', ''),
            media_class=media_class,
            state=info.get('state', ''),
            binary=props.get('application.process.binary', ''),
        ))

    return nodes


async def nodes() -> list[Node]:
    return parse_nodes(await _run(PW_DUMP))


async def streams() -> list[Node]:
    """Playback streams only -- what applications are producing."""
    return [n for n in await nodes() if n.media_class == STREAM_OUTPUT]


def match(candidates: list[Node], *,
          application: str = '',
          name: str = '',
          binary: str = '') -> Node | None:
    """
    Find a node by property, most specific match first.

    Every supplied term is tried against every field, because what
    lands on the graph depends on which backend the player used.
    PULSE_PROP only reaches PipeWire through the Pulse compatibility
    layer -- sox built against ALSA ignores it entirely and shows up
    as "SoX" instead.

    Matching is case-insensitive: sox reports "SoX", not "sox".
    """
    terms = [t for t in (application, name, binary) if t]
    if not terms:
        return None

    def fields(node: Node) -> list[str]:
        return [node.application, node.name, node.binary]

    # Exact, case-insensitive, across all fields.
    for term in terms:
        lowered = term.lower()
        for node in candidates:
            if any(f and f.lower() == lowered for f in fields(node)):
                return node

    # Substring, for players that decorate the name.
    for term in terms:
        lowered = term.lower()
        for node in candidates:
            haystack = ' '.join(f for f in fields(node) if f).lower()
            if lowered in haystack:
                return node

    return None


async def find(application: str = '', name: str = '',
               binary: str = '', retries: int = 6,
               delay: float = 0.5) -> Node:
    """
    Locate a stream, waiting for it to appear.

    A pipeline started a moment ago may not have registered with
    PipeWire yet, so this retries rather than failing on the first
    look.
    """
    for attempt in range(retries):
        found = match(await streams(), application=application,
                      name=name, binary=binary)
        if found is not None:
            return found
        if attempt < retries - 1:
            await asyncio.sleep(delay)

    raise NotFoundError(
        'stream', application or name or binary,
        [f'{n.application or n.name} ({n.id})' for n in await streams()])


async def exists(node_id: int) -> bool:
    """Whether a node id still refers to something."""
    return any(n.id == node_id for n in await nodes())


async def set_mute(node_id: int, muted: bool) -> None:
    await _run(WPCTL, 'set-mute', str(node_id), '1' if muted else '0')


async def set_volume(node_id: int, percent: int) -> None:
    percent = max(0, min(150, int(percent)))
    await _run(WPCTL, 'set-volume', str(node_id), f'{percent}%')


async def get_volume(node_id: int) -> tuple[int, bool]:
    """Returns (percent, muted)."""
    import re
    out = await _run(WPCTL, 'get-volume', str(node_id))
    matched = re.search(r'Volume:\s*([\d.]+)', out)
    percent = round(float(matched.group(1)) * 100) if matched else 0
    return percent, '[MUTED]' in out.upper()
