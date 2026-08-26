"""
FM broadcast radio via RTL-SDR.

Playback is `rtl_fm` piped to `play`, which is a long-running pipeline
rather than a command that returns. That makes process lifecycle the
main problem this module solves: the CLI has to be able to start the
radio and exit, and a later invocation has to find and stop it.

The pipeline runs in its own session (setsid) with its PID recorded in
XDG_RUNTIME_DIR. Signalling the process *group* is what stops both
halves -- killing the shell alone leaves rtl_fm orphaned and still
holding the USB device, which then blocks the next tune with a
confusing "device busy".

Requires:
    pacman -S rtl-sdr sox

The RTL-SDR Blog V4 needs a recent librtlsdr -- older builds do not
know the R828D tuner and either fail to open the device or tune to the
wrong frequency. `rtl_test` naming the tuner is the quick check.
"""

import os
import json
import time
import signal
import asyncio
from pathlib import Path
from dataclasses import dataclass, field, asdict

from carlib.core.errors import NotAvailableError, NotFoundError

RTL_FM = 'rtl_fm'
RTL_TEST = 'rtl_test'
PLAY = 'play'

# FM broadcast band. Japan and a few other places differ, but this is
# the ITU Region 1 allocation.
FM_MIN = 87.5
FM_MAX = 108.0

# rtl_fm demodulates at 200k then resamples; 48k is what the pipe
# carries to the player.
DEMOD_RATE = 200_000
AUDIO_RATE = 48_000

DEFAULT_GAIN = 40.0

# How long to wait for the pipeline to prove it started. rtl_fm exits
# almost immediately on a bad device or busy USB, so a short settle is
# enough to catch it.
START_SETTLE = 1.5


def _runtime_dir() -> Path:
    base = os.environ.get('XDG_RUNTIME_DIR')
    if base:
        return Path(base)
    return Path('/tmp')


STATE_FILE = _runtime_dir() / 'carlib-fm.json'
PRESET_FILE = (
    Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config'))
    / 'carlib' / 'fm-presets.json'
)


@dataclass
class Station:
    frequency: float
    name: str = ''

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def label(self) -> str:
        return self.name or f'{self.frequency:.1f}'


@dataclass
class RadioState:
    playing: bool = False
    frequency: float | None = None
    name: str = ''
    gain: float = DEFAULT_GAIN
    pid: int | None = None
    started: float | None = None

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def label(self) -> str:
        if not self.playing or self.frequency is None:
            return 'off'
        if self.name:
            return f'{self.name}  {self.frequency:.1f}'
        return f'{self.frequency:.1f} FM'

    @property
    def uptime(self) -> int:
        if not self.started:
            return 0
        return int(time.time() - self.started)


# --- Frequency handling ----------------------------------------------------

def parse_frequency(value: str | float | int) -> float:
    """
    Accept the ways people actually write a frequency.

        92.7        -> 92.7
        '92.7'      -> 92.7
        '92,7'      -> 92.7     (Swedish decimal comma)
        '92.7M'     -> 92.7
        '92700000'  -> 92.7     (Hz)
        '92700'     -> 92.7     (kHz)

    Raises ValueError rather than guessing when the result falls
    outside the broadcast band -- tuning 9.27 MHz because someone
    misplaced a decimal is worse than an error.
    """
    if isinstance(value, (int, float)):
        mhz = float(value)
    else:
        text = str(value).strip().lower().replace(',', '.')
        text = text.removesuffix('hz').removesuffix('fm').strip()

        multiplier = 1.0
        if text.endswith('m'):
            text = text[:-1]
        elif text.endswith('k'):
            text = text[:-1]
            multiplier = 1e-3

        try:
            number = float(text)
        except ValueError as exc:
            raise ValueError(f'not a frequency: {value!r}') from exc

        mhz = number * multiplier

        # Bare integers are ambiguous. Scale down until it lands in a
        # plausible range rather than rejecting 92700000 outright.
        while mhz > FM_MAX * 10:
            mhz /= 1000.0

    mhz = round(mhz, 2)

    if not FM_MIN <= mhz <= FM_MAX:
        raise ValueError(
            f'{mhz} MHz is outside the FM band '
            f'({FM_MIN}-{FM_MAX} MHz)')

    return mhz


# --- Presets ---------------------------------------------------------------

def load_presets() -> list[Station]:
    if not PRESET_FILE.exists():
        return []
    try:
        raw = json.loads(PRESET_FILE.read_text())
    except (OSError, json.JSONDecodeError):
        return []

    stations = []
    for entry in raw:
        try:
            stations.append(Station(
                frequency=float(entry['frequency']),
                name=entry.get('name', ''),
            ))
        except (KeyError, TypeError, ValueError):
            continue

    stations.sort(key=lambda s: s.frequency)
    return stations


def save_presets(stations: list[Station]) -> None:
    PRESET_FILE.parent.mkdir(parents=True, exist_ok=True)
    PRESET_FILE.write_text(json.dumps(
        [s.to_dict() for s in stations], indent=2, ensure_ascii=False))


def add_preset(frequency: float, name: str = '') -> list[Station]:
    """Add or rename a preset. Frequency is the key."""
    stations = [s for s in load_presets()
                if abs(s.frequency - frequency) > 0.01]
    stations.append(Station(frequency=frequency, name=name))
    stations.sort(key=lambda s: s.frequency)
    save_presets(stations)
    return stations


def remove_preset(frequency: float) -> list[Station]:
    stations = load_presets()
    kept = [s for s in stations if abs(s.frequency - frequency) > 0.01]
    if len(kept) == len(stations):
        raise NotFoundError('preset', f'{frequency:.1f}',
                            [s.label for s in stations])
    save_presets(kept)
    return kept


def find_preset(frequency: float) -> Station | None:
    for station in load_presets():
        if abs(station.frequency - frequency) < 0.01:
            return station
    return None


def resolve_station(value: str) -> Station:
    """
    Turn a frequency or a preset name into a Station.

    Tries presets by name first, so `fm play P3` works, then falls back
    to parsing it as a frequency.
    """
    presets = load_presets()

    lowered = str(value).strip().lower()
    for station in presets:
        if station.name.lower() == lowered:
            return station
    for station in presets:
        if station.name and lowered in station.name.lower():
            return station

    frequency = parse_frequency(value)
    existing = find_preset(frequency)
    return existing or Station(frequency=frequency)


# --- Process state ---------------------------------------------------------

def _read_state() -> dict:
    if not STATE_FILE.exists():
        return {}
    try:
        return json.loads(STATE_FILE.read_text())
    except (OSError, json.JSONDecodeError):
        return {}


def _write_state(data: dict) -> None:
    try:
        STATE_FILE.write_text(json.dumps(data))
    except OSError:
        pass


def _clear_state() -> None:
    try:
        STATE_FILE.unlink()
    except OSError:
        pass


def _alive(pid: int) -> bool:
    """Whether the process group still exists."""
    try:
        os.killpg(os.getpgid(pid), 0)
        return True
    except (ProcessLookupError, PermissionError, OSError):
        return False


# --- Device ----------------------------------------------------------------

async def devices() -> list[str]:
    """
    RTL-SDR dongles rtl_test can see.

    rtl_test writes its device list to stderr and then blocks reading
    samples, so this starts it, reads what it needs and kills it.
    """
    try:
        proc = await asyncio.create_subprocess_exec(
            RTL_TEST,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
    except FileNotFoundError as exc:
        raise NotAvailableError(
            'rtl_test not found',
            hint='pacman -S rtl-sdr') from exc

    found = []
    try:
        while True:
            line = await asyncio.wait_for(proc.stdout.readline(),
                                          timeout=3.0)
            if not line:
                break
            text = line.decode(errors='replace').strip()
            # Device lines look like:  0:  RTLSDRBlog, Blog V4, SN: ...
            if text and text[0].isdigit() and ':' in text:
                found.append(text.split(':', 1)[1].strip())
            if 'Reading samples' in text:
                break
    except asyncio.TimeoutError:
        pass
    finally:
        try:
            proc.kill()
            await proc.wait()
        except ProcessLookupError:
            pass

    return found


# --- Playback --------------------------------------------------------------

def build_command(frequency: float, gain: float = DEFAULT_GAIN,
                  device: int = 0, squelch: int = 0) -> str:
    """
    The rtl_fm pipeline, as a shell string.

    A shell is used rather than two coupled subprocesses because the
    pipe between them is what does the work, and letting the shell own
    it means one process group to signal.
    """
    return (
        f'{RTL_FM} -d {device} -f {frequency:.1f}M -M wbfm '
        f'-s {DEMOD_RATE} -r {AUDIO_RATE} -g {gain:g} -l {squelch} '
        f'| {PLAY} -q -r {AUDIO_RATE} -t raw -e s -b 16 -c 1 -'
    )


async def status() -> RadioState:
    """What is playing, if anything."""
    data = _read_state()
    pid = data.get('pid')

    if not pid or not _alive(pid):
        if data:
            _clear_state()      # stale entry from a crash
        return RadioState(playing=False)

    frequency = data.get('frequency')
    name = data.get('name', '')

    # Pick up a preset name added since playback started.
    if frequency is not None and not name:
        preset = find_preset(frequency)
        if preset:
            name = preset.name

    return RadioState(
        playing=True,
        frequency=frequency,
        name=name,
        gain=data.get('gain', DEFAULT_GAIN),
        pid=pid,
        started=data.get('started'),
    )


async def stop() -> RadioState:
    """
    Stop playback.

    Signals the whole process group: killing the shell alone leaves
    rtl_fm holding the USB device, and the next tune then fails with
    'device busy'.
    """
    data = _read_state()
    pid = data.get('pid')

    if pid and _alive(pid):
        try:
            os.killpg(os.getpgid(pid), signal.SIGTERM)
        except (ProcessLookupError, PermissionError, OSError):
            pass

        # Give it a moment, then insist.
        for _ in range(20):
            if not _alive(pid):
                break
            await asyncio.sleep(0.1)
        else:
            try:
                os.killpg(os.getpgid(pid), signal.SIGKILL)
            except (ProcessLookupError, PermissionError, OSError):
                pass

    _clear_state()
    return RadioState(playing=False)


async def play(station: Station | float | str,
               gain: float = DEFAULT_GAIN,
               device: int = 0,
               squelch: int = 0) -> RadioState:
    """
    Tune and start playing. Replaces whatever was playing before.

    Only one RTL-SDR stream can run at a time, so this stops the
    existing pipeline first rather than failing on a busy device.
    """
    if isinstance(station, Station):
        target = station
    elif isinstance(station, (int, float)):
        frequency = parse_frequency(station)
        target = find_preset(frequency) or Station(frequency=frequency)
    else:
        target = resolve_station(station)

    await stop()

    command = build_command(target.frequency, gain, device, squelch)

    try:
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
            start_new_session=True,     # own process group, so killpg works
        )
    except FileNotFoundError as exc:
        raise NotAvailableError(
            'cannot start playback',
            hint='pacman -S rtl-sdr sox') from exc

    _write_state({
        'pid': proc.pid,
        'frequency': target.frequency,
        'name': target.name,
        'gain': gain,
        'device': device,
        'started': time.time(),
    })

    # rtl_fm exits almost immediately on a missing or busy device, so
    # a short settle catches the common failures rather than reporting
    # success for a pipeline that already died.
    await asyncio.sleep(START_SETTLE)

    if not _alive(proc.pid):
        _clear_state()
        raise NotAvailableError(
            f'playback stopped immediately on {target.frequency:.1f} MHz',
            hint='check `rtl_test` sees the dongle and nothing else is '
                 'using it, and that sox is installed')

    return await status()


async def tune(offset: float) -> RadioState:
    """
    Step the frequency without restarting from scratch.

    Nothing about rtl_fm supports retuning a running process, so this
    is stop-and-start -- but it keeps the gain and device settings.
    """
    current = await status()
    if not current.playing or current.frequency is None:
        raise NotAvailableError('nothing is playing')

    frequency = parse_frequency(current.frequency + offset)
    return await play(frequency, gain=current.gain)


async def next_preset(step: int = 1) -> RadioState:
    """Move to the next preset up or down, wrapping around."""
    presets = load_presets()
    if not presets:
        raise NotFoundError('preset', 'any', [])

    current = await status()
    if not current.playing or current.frequency is None:
        return await play(presets[0])

    index = 0
    for i, station in enumerate(presets):
        if abs(station.frequency - current.frequency) < 0.01:
            index = i
            break

    return await play(presets[(index + step) % len(presets)],
                      gain=current.gain)
