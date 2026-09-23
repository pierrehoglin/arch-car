"""
PipeWire node lookup and per-stream volume.

Muting one stream needs its node id, and PipeWire assigns those
sequentially at runtime: they change on every restart, differ between
machines, and a fresh one is issued each time a stream is created.
There is nothing stable to hard-code.

What is stable is the id for the lifetime of a stream. So the pattern
is resolve once when the stream starts, cache it, and re-resolve only
when an operation fails -- which is what a stale id looks like.

Streams are found by their PipeWire properties. Tag a stream at
launch and it can be found again:

    pw-play -P '{ node.name = "carlib-fm" }' ...

Requires pipewire and wireplumber, both already needed for audio.
"""

import json
import math
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
    # None where the graph did not report a volume -- params are not
    # always enumerated, and a node that has never played may have
    # none. Distinguished from zero, which is a real silence.
    percent: int | None = None
    muted: bool = False

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


def _linear(cubed: float) -> int:
    """A stored channel volume as the percentage a person means."""
    return round(math.cbrt(max(0.0, cubed)) * 100)


def _volume_of(info: dict) -> tuple[int | None, bool]:
    """
    A node's level, out of info.params.Props.

    channelVolumes holds one float per channel, where 1.0 is full.
    The loudest channel is taken: the alternative is an average, and
    a node panned hard to one side would then read as half volume.

    The values are cubed. A node at 80% stores 0.512, and at 32% it
    stores 0.033 -- so reading them directly makes everything look far
    quieter than it is, and worse the lower it goes. The cube root
    undoes it.

    Note this is the opposite of `wpctl`, which prints the linear
    value: [vol: 0.47] really is 47%. Device levels come from wpctl
    and need no correction; only what is read out of the graph does.
    """
    params = info.get('params') or {}
    entries = params.get('Props') or []
    if not entries or not isinstance(entries[0], dict):
        return None, False

    props = entries[0]
    volumes = props.get('channelVolumes')
    muted = bool(props.get('mute', False))

    if not isinstance(volumes, list) or not volumes:
        # Mono nodes and some filters report a single volume instead.
        single = props.get('volume')
        if isinstance(single, (int, float)):
            return _linear(float(single)), muted
        return None, muted

    return _linear(max(float(v) for v in volumes)), muted


def parse_nodes(text: str) -> list[Node]:
    """
    Pull audio nodes out of `pw-dump` output.

    pw-dump emits every object on the graph -- nodes, ports, links,
    devices, factories. Only Node objects with a media class matter
    here, and properties are nested under info.props.

    Volume comes from the same objects, under info.params.Props, so
    reading it costs nothing beyond the call already being made. A
    wpctl invocation per stream would be a subprocess each, several
    times a second while a slider is moving.
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

        percent, muted = _volume_of(info)

        nodes.append(Node(
            id=int(entry.get('id', 0)),
            name=props.get('node.name', ''),
            application=props.get('application.name', ''),
            media_class=media_class,
            state=info.get('state', ''),
            binary=props.get('application.process.binary', ''),
            percent=percent,
            muted=muted,
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
    Find a node by property, exact and case-insensitive.

    Every supplied term is tried against every field, because which
    property carries the tag depends on how the stream was created.

    Deliberately exact: with pw-play setting node.name explicitly
    there is nothing to be lenient about, and a substring match could
    grab the wrong stream.
    """
    terms = [t for t in (application, name, binary) if t]
    if not terms:
        return None

    for term in terms:
        lowered = term.lower()
        for node in candidates:
            fields = (node.application, node.name, node.binary)
            if any(f and f.lower() == lowered for f in fields):
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
