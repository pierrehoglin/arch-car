"""
Audio volume via PipeWire.

PipeWire has no stable D-Bus API for volume -- it uses its own protocol
over a native socket, and WirePlumber exposes nothing useful on the
bus either. PulseAudio's D-Bus module is not loaded by default and is
deprecated regardless.

So this shells out to wpctl, which ships with WirePlumber and is the
supported control surface. Subprocesses run through asyncio.

Note this runs against the *user session's* PipeWire. A system service
will not find it without XDG_RUNTIME_DIR set -- run anything using this
as a user unit.
"""

import re
import asyncio
from dataclasses import dataclass, asdict

from carlib.core.errors import NotAvailableError

WPCTL = 'wpctl'

SINK = '@DEFAULT_AUDIO_SINK@'
SOURCE = '@DEFAULT_AUDIO_SOURCE@'

# wpctl caps at 1.0 by default but will go higher, which distorts.
MAX_VOLUME = 100


@dataclass
class Volume:
    percent: int = 0
    muted: bool = False
    target: str = 'sink'

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def bars(self) -> str:
        filled = min(10, max(0, round(self.percent / 10)))
        return '#' * filled + '.' * (10 - filled)


@dataclass
class AudioDevice:
    node_id: int
    name: str
    is_default: bool = False
    kind: str = 'sink'

    def to_dict(self) -> dict:
        return asdict(self)


async def _run(*args: str, timeout: float = 10.0) -> str:
    try:
        proc = await asyncio.create_subprocess_exec(
            WPCTL, *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError as exc:
        raise NotAvailableError(
            'wpctl not found',
            hint='install wireplumber') from exc

    try:
        out, err = await asyncio.wait_for(proc.communicate(),
                                          timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        raise NotAvailableError(f'wpctl timed out: {" ".join(args)}')

    if proc.returncode != 0:
        message = err.decode(errors='replace').strip() or 'unknown error'
        raise NotAvailableError(
            f'wpctl failed: {message}',
            hint='is PipeWire running in this session? A system '
                 'service needs XDG_RUNTIME_DIR set.')

    return out.decode(errors='replace')


def parse_volume(text: str, target: str = 'sink') -> Volume:
    """
    Parse `wpctl get-volume` output.

    Format is 'Volume: 0.65' or 'Volume: 0.65 [MUTED]'. The value is a
    float where 1.0 is 100%, and it can exceed 1.0.
    """
    match = re.search(r'Volume:\s*([\d.]+)', text)
    if not match:
        raise NotAvailableError(f'cannot parse wpctl output: {text!r}')

    percent = round(float(match.group(1)) * 100)
    return Volume(
        percent=percent,
        muted='[MUTED]' in text.upper(),
        target=target,
    )


def parse_status(text: str) -> list[AudioDevice]:
    """
    Pull sinks and sources out of `wpctl status`.

    wpctl draws a box-drawing tree, so lines look like:

        |  *   47. Built-in Audio            [vol: 0.65]

    Those characters have to be stripped before anything else, and the
    section headings carry them too.
    """
    devices = []
    section = None

    # Everything wpctl uses to draw the tree.
    tree_chars = '\u2502\u251c\u2514\u2500\u2551\u2560\u255a|'

    for raw_line in text.splitlines():
        line = raw_line.strip(tree_chars + ' \t')
        if not line:
            continue

        lowered = line.lower()
        if lowered.startswith('sinks:'):
            section = 'sink'
            continue
        if lowered.startswith('sources:'):
            section = 'source'
            continue
        # Any other heading ends the section.
        if line.endswith(':') and not line[0].isdigit():
            section = None
            continue

        if section is None:
            continue

        match = re.match(r'(\*)?\s*(\d+)\.\s+(.+?)\s*(\[.*\])?$', line)
        if not match:
            continue

        name = match.group(3).strip()
        if not name:
            continue

        devices.append(AudioDevice(
            node_id=int(match.group(2)),
            name=name,
            is_default=match.group(1) == '*',
            kind=section,
        ))

    return devices


async def get(target: str = SINK) -> Volume:
    """Current volume of the default sink, or a named target."""
    out = await _run('get-volume', target)
    kind = 'source' if target == SOURCE else 'sink'
    return parse_volume(out, kind)


async def set_volume(percent: int, target: str = SINK) -> Volume:
    """Set volume as a percentage, clamped to avoid distortion."""
    percent = max(0, min(MAX_VOLUME, int(percent)))
    await _run('set-volume', target, f'{percent}%')
    return await get(target)


async def adjust(delta: int, target: str = SINK) -> Volume:
    """
    Step the volume up or down.

    Clamping is done here rather than with wpctl's own +/- syntax,
    which will happily run past 100% into distortion.
    """
    current = await get(target)
    return await set_volume(current.percent + delta, target)


async def set_muted(muted: bool, target: str = SINK) -> Volume:
    await _run('set-mute', target, '1' if muted else '0')
    return await get(target)


async def toggle_mute(target: str = SINK) -> Volume:
    await _run('set-mute', target, 'toggle')
    return await get(target)


async def devices() -> list[AudioDevice]:
    """All sinks and sources, with the default marked."""
    return parse_status(await _run('status'))


async def set_default(node_id: int) -> list[AudioDevice]:
    """Switch the default sink, e.g. from onboard to a USB DAC."""
    await _run('set-default', str(node_id))
    return await devices()


async def microphone() -> Volume:
    return await get(SOURCE)


async def set_microphone(percent: int) -> Volume:
    return await set_volume(percent, SOURCE)
