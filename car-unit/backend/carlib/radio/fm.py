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
RTL_POWER = 'rtl_power'
REDSEA = 'redsea'
SOX = 'sox'
PLAY = 'play'

# FM broadcast band. Japan and a few other places differ, but this is
# the ITU Region 1 allocation.
FM_MIN = 87.5
FM_MAX = 108.0

# rtl_fm demodulates at 200k then resamples; 48k is what the pipe
# carries to the player.
DEMOD_RATE = 200_000
AUDIO_RATE = 48_000

# RDS needs the raw MPX composite at redsea's native rate. This is a
# different demodulator mode (-M fm, not -M wbfm) and a different rate,
# which is why RDS and plain playback cannot share one rtl_fm.
MPX_RATE = 171_000

# Audio is the mono sum below 15 kHz; the 19 kHz pilot, 38 kHz stereo
# subcarrier and 57 kHz RDS carrier all sit above it and get filtered
# out. That makes playback mono -- rtl_fm has no stereo decoder.
AUDIO_LOWPASS = 15_000

# redsea writes RDS groups to stderr when feeding audio through, so
# they go to a file the status reader drains.
RDS_MAX_BYTES = 1 << 20

# Band scanning. 100 kHz bins match European channel spacing; a
# station occupies roughly 200 kHz so it lands across two or three.
SCAN_BIN_HZ = 100_000
SCAN_INTEGRATION = 2          # seconds per sweep
SCAN_THRESHOLD_DB = 8.0       # above the noise floor to count as a station
SCAN_SEPARATION_MHZ = 0.3     # peaks closer than this are one station
SCAN_FLOOR_WINDOW = 1.5       # MHz either side for the local noise floor
SCAN_CACHE_SECONDS = 900      # re-sweep if the cache is older than this

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
RDS_FILE = _runtime_dir() / 'carlib-fm-rds.jsonl'
SCAN_FILE = _runtime_dir() / 'carlib-fm-scan.json'
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
class Rds:
    """
    Decoded RDS, accumulated from the group stream.

    Each redsea line is one group carrying a fragment, so nothing here
    arrives in a single message -- the fields fill in over a few
    seconds as groups repeat.
    """

    pi: str = ''                    # station id, stable
    ps: str = ''                    # 8-char station name
    radiotext: str = ''             # 64-char now-playing or slogan
    program_type: str = ''
    alt_frequencies: list[float] = field(default_factory=list)
    traffic_program: bool = False   # station carries traffic news
    traffic_announcement: bool = False   # bulletin on air NOW
    is_music: bool | None = None
    stereo: bool | None = None
    groups: int = 0

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def name(self) -> str:
        return self.ps

    @property
    def has_data(self) -> bool:
        return bool(self.pi or self.ps or self.radiotext)


def parse_rds(text: str, into: 'Rds | None' = None) -> Rds:
    """
    Fold redsea's newline-delimited JSON into one Rds.

    Later values win, so replaying the whole stream leaves the most
    recent state. Fields absent from a group are left alone rather
    than cleared -- PS appears in maybe one group in ten, and blanking
    it in between would make the display flicker.
    """
    rds = into or Rds()

    for line in text.splitlines():
        line = line.strip()
        if not line or not line.startswith('{'):
            continue
        try:
            group = json.loads(line)
        except json.JSONDecodeError:
            continue

        rds.groups += 1

        if 'pi' in group:
            rds.pi = str(group['pi'])
        if 'prog_type' in group:
            rds.program_type = str(group['prog_type'])
        if 'tp' in group:
            rds.traffic_program = bool(group['tp'])
        if 'ta' in group:
            rds.traffic_announcement = bool(group['ta'])
        if 'is_music' in group:
            rds.is_music = bool(group['is_music'])

        # PS is transmitted space-padded to 8 characters.
        for key in ('ps', 'partial_ps'):
            if key in group:
                value = str(group[key]).strip()
                if value:
                    rds.ps = value
                break

        for key in ('radiotext', 'partial_radiotext'):
            if key in group:
                value = str(group[key]).strip()
                if value:
                    rds.radiotext = value
                break

        # redsea reports AF in kHz.
        for key in ('alt_frequencies_a', 'alt_frequencies_b',
                    'partial_alt_frequencies_a'):
            if key in group and group[key]:
                try:
                    freqs = sorted({round(float(f) / 1000.0, 1)
                                    for f in group[key]})
                except (TypeError, ValueError):
                    continue
                rds.alt_frequencies = freqs
                break

        di = group.get('di')
        if isinstance(di, dict) and 'stereo' in di:
            rds.stereo = bool(di['stereo'])

    return rds


def read_rds() -> Rds:
    """
    Drain the RDS file into an Rds, then truncate it.

    Truncating on read bounds the file: it lives in XDG_RUNTIME_DIR,
    which is tmpfs, and redsea emits roughly 1.5 kB/s. Anything that
    polls -- a status bar, the CLI -- keeps it small. The size cap
    handles the case where nothing polls for hours.
    """
    if not RDS_FILE.exists():
        return Rds()

    try:
        size = RDS_FILE.stat().st_size
        with open(RDS_FILE, 'r', errors='replace') as handle:
            if size > RDS_MAX_BYTES:
                handle.seek(size - RDS_MAX_BYTES)
                handle.readline()       # discard the partial line
            text = handle.read()
        # Truncate rather than delete: redsea holds the fd open, and
        # unlinking would leave it writing to a file nobody can read.
        with open(RDS_FILE, 'w'):
            pass
    except OSError:
        return Rds()

    return parse_rds(text)


@dataclass
class RadioState:
    playing: bool = False
    frequency: float | None = None
    name: str = ''
    gain: float = DEFAULT_GAIN
    pid: int | None = None
    started: float | None = None
    rds: Rds = field(default_factory=Rds)

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def label(self) -> str:
        if not self.playing or self.frequency is None:
            return 'off'
        # RDS wins over a saved preset name -- it is what the station
        # currently calls itself.
        name = self.rds.ps or self.name
        if name:
            return f'{name}  {self.frequency:.1f}'
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
        '92.7M'     -> 92.7
        '92700000'  -> 92.7     (Hz)
        '92700k'    -> 92.7     (kHz)

    Raises ValueError rather than guessing when the result falls
    outside the broadcast band -- tuning 9.27 MHz because someone
    misplaced a decimal is worse than an error.
    """
    if isinstance(value, (int, float)):
        mhz = float(value)
    else:
        text = str(value).strip().lower()
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


def _alive(pgid: int) -> bool:
    """
    Whether any process in the group is still running.

    The recorded pid IS the process group id, because the pipeline is
    started with start_new_session=True. Using it directly rather than
    calling os.getpgid() matters: the shell often exits while rtl_fm
    and play keep running, and os.getpgid() on a dead leader raises --
    which would report the radio as stopped while it is still playing.
    """
    try:
        os.killpg(pgid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True         # exists, owned by someone else
    except OSError:
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
                  device: int = 0, squelch: int = 0,
                  rds: bool = True) -> str:
    """
    The playback pipeline, as a shell string.

    A shell is used rather than coupled subprocesses because the pipes
    are what do the work, and letting the shell own them means one
    process group to signal.

    With RDS, rtl_fm runs in raw MPX mode and redsea sits in the middle
    with --feed-through: it echoes the signal onward and writes decoded
    groups to stderr. sox then filters the composite down to the mono
    audio and resamples for the player.

    Without RDS it is the simpler wbfm path, which costs less CPU.
    """
    if not rds:
        return (
            f'{RTL_FM} -d {device} -f {frequency:.1f}M -M wbfm '
            f'-s {DEMOD_RATE} -r {AUDIO_RATE} -g {gain:g} -l {squelch} '
            f'| {PLAY} -q -r {AUDIO_RATE} -t raw -e s -b 16 -c 1 -'
        )

    return (
        f'{RTL_FM} -d {device} -f {frequency:.1f}M -M fm -l {squelch} '
        f'-A std -p 0 -s {MPX_RATE} -g {gain:g} -F 9 - '
        f'| {REDSEA} -e -r {MPX_RATE} 2>>"{RDS_FILE}" '
        f'| {SOX} -q -r {MPX_RATE} -t raw -e s -b 16 -c 1 - '
        f'-t raw -r {AUDIO_RATE} - lowpass {AUDIO_LOWPASS} '
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

    # Drain any new RDS groups and merge them into what we already
    # know. Cached in the state file so a fresh read does not lose the
    # station name between polls.
    cached = data.get('rds') or {}
    rds = Rds(**{k: v for k, v in cached.items()
                 if k in Rds.__dataclass_fields__})

    if data.get('rds_enabled', True):
        fresh = read_rds()
        if fresh.groups:
            rds = parse_rds('', into=rds)
            for name_, value in vars(fresh).items():
                if name_ == 'groups':
                    rds.groups += value
                elif value not in ('', None, [], False):
                    setattr(rds, name_, value)
            data['rds'] = rds.to_dict()
            _write_state(data)

    return RadioState(
        playing=True,
        frequency=frequency,
        name=name,
        gain=data.get('gain', DEFAULT_GAIN),
        pid=pid,
        started=data.get('started'),
        rds=rds,
    )


async def stop() -> RadioState:
    """
    Stop playback.

    Signals the whole process group: killing the shell alone leaves
    rtl_fm holding the USB device, and the next tune then fails with
    'device busy'.
    """
    data = _read_state()
    pgid = data.get('pid')

    if pgid and _alive(pgid):
        try:
            os.killpg(pgid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError, OSError):
            pass

        # Give it a moment, then insist. rtl_fm can sit in a USB read
        # and ignore SIGTERM until that returns.
        for _ in range(20):
            if not _alive(pgid):
                break
            await asyncio.sleep(0.1)
        else:
            try:
                os.killpg(pgid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError, OSError):
                pass
            await asyncio.sleep(0.2)

    _clear_state()
    return RadioState(playing=False)


async def play(station: Station | float | str,
               gain: float = DEFAULT_GAIN,
               device: int = 0,
               squelch: int = 0,
               rds: bool = True) -> RadioState:
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

    previous = _read_state().get('pid')
    await stop()

    # The USB device is not free the instant the process group dies --
    # the kernel has to tear the transfers down. Starting rtl_fm too
    # soon gives 'usb_claim_interface error -6' and the new pipeline
    # exits immediately, which looks like a tuning failure.
    if previous:
        for _ in range(20):
            if not _alive(previous):
                break
            await asyncio.sleep(0.1)
        await asyncio.sleep(0.3)

    # Start with an empty RDS file so the previous station's
    # groups are not attributed to this one.
    try:
        RDS_FILE.write_text('')
    except OSError:
        pass

    command = build_command(target.frequency, gain, device,
                            squelch, rds)

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
            hint='pacman -S rtl-sdr sox, and build redsea') from exc

    _write_state({
        'pid': proc.pid,
        'frequency': target.frequency,
        'name': target.name,
        'gain': gain,
        'device': device,
        'started': time.time(),
        'rds_enabled': rds,
        'rds': {},
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
                 'using it, and that sox and redsea are installed. '
                 'Try rds=False to rule out redsea.')

    return await status()


# --- Band scanning ---------------------------------------------------------

@dataclass
class Signal:
    """A peak found while sweeping the band."""

    frequency: float
    power: float = 0.0          # dB above the noise floor
    name: str = ''

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def label(self) -> str:
        return self.name or f'{self.frequency:.1f}'

    @property
    def bars(self) -> str:
        """Signal strength as a five-step bar, 0-30 dB over the floor."""
        filled = min(5, max(0, round(self.power / 6)))
        return '#' * filled + '.' * (5 - filled)


def parse_power_csv(text: str) -> list[tuple[float, float]]:
    """
    Parse rtl_power CSV into (MHz, dB) pairs.

    Each row is:
        date, time, freq_low, freq_high, freq_step, samples, db, db, ...

    Bin N covers freq_low + N * freq_step.
    """
    bins = []

    for line in text.splitlines():
        parts = [p.strip() for p in line.split(',')]
        if len(parts) < 7:
            continue
        try:
            low = float(parts[2])
            step = float(parts[4])
        except ValueError:
            continue

        for index, value in enumerate(parts[6:]):
            try:
                power = float(value)
            except ValueError:
                continue
            bins.append((round((low + index * step) / 1e6, 4), power))

    bins.sort(key=lambda b: b[0])
    return bins


def _median(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2.0


def find_signals(bins: list[tuple[float, float]],
                 threshold: float = SCAN_THRESHOLD_DB,
                 separation: float = SCAN_SEPARATION_MHZ,
                 window: float = SCAN_FLOOR_WINDOW) -> list[Signal]:
    """
    Pick stations out of a sweep.

    The noise floor is measured locally -- a median over a window
    either side of each bin -- rather than once across the whole band.
    A global median breaks when part of the band sits elevated: on this
    hardware 105.5-108 MHz runs about 15 dB hot from interference,
    which drags a global floor up, hides real stations elsewhere and
    makes the results move around as the threshold changes.

    Peaks within `separation` are treated as one station, since a
    200 kHz signal lands across several 100 kHz bins.
    """
    if not bins:
        return []

    powers = [power for _, power in bins]
    freqs = [freq for freq, _ in bins]

    candidates = []
    for index, (freq, power) in enumerate(bins):
        if not FM_MIN <= freq <= FM_MAX:
            continue

        # Bins within the window, by frequency rather than index, so
        # gaps in the sweep do not distort it.
        low = freq - window
        high = freq + window
        start = index
        while start > 0 and freqs[start - 1] >= low:
            start -= 1
        end = index
        while end < len(freqs) - 1 and freqs[end + 1] <= high:
            end += 1

        local = _median(powers[start:end + 1])
        if power - local >= threshold:
            candidates.append((freq, power - local))

    if not candidates:
        return []

    signals = []
    group = [candidates[0]]

    for freq, power in candidates[1:]:
        if freq - group[-1][0] <= separation:
            group.append((freq, power))
        else:
            signals.append(_peak(group))
            group = [(freq, power)]
    signals.append(_peak(group))

    return signals


def _peak(group: list[tuple[float, float]]) -> Signal:
    """Strongest bin in a group, snapped to the 100 kHz channel grid."""
    frequency, power = max(group, key=lambda item: item[1])
    return Signal(frequency=round(frequency, 1), power=round(power, 1))


def load_scan() -> tuple[list[Signal], float]:
    """Cached scan results and when they were taken."""
    if not SCAN_FILE.exists():
        return [], 0.0
    try:
        data = json.loads(SCAN_FILE.read_text())
    except (OSError, json.JSONDecodeError):
        return [], 0.0

    signals = []
    for entry in data.get('signals', []):
        try:
            signals.append(Signal(
                frequency=float(entry['frequency']),
                power=float(entry.get('power', 0.0)),
                name=entry.get('name', ''),
            ))
        except (KeyError, TypeError, ValueError):
            continue

    return signals, float(data.get('taken', 0.0))


def save_scan(signals: list[Signal]) -> None:
    try:
        SCAN_FILE.write_text(json.dumps({
            'taken': time.time(),
            'signals': [s.to_dict() for s in signals],
        }))
    except OSError:
        pass


async def scan(threshold: float = SCAN_THRESHOLD_DB,
               integration: int = SCAN_INTEGRATION,
               device: int = 0,
               gain: float = DEFAULT_GAIN,
               resume: bool = True) -> list[Signal]:
    """
    Sweep the FM band for stations.

    One dongle cannot sweep and play at once, so playback stops for the
    duration and restarts afterwards unless resume=False. A sweep takes
    roughly `integration` seconds plus overhead.
    """
    previous = await status()

    if previous.playing:
        await stop()

    try:
        proc = await asyncio.create_subprocess_exec(
            RTL_POWER,
            '-d', str(device),
            '-f', f'{FM_MIN}M:{FM_MAX}M:{SCAN_BIN_HZ}',
            '-g', f'{gain:g}',
            '-i', str(integration),
            '-1',
            '-',
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
    except FileNotFoundError as exc:
        raise NotAvailableError(
            'rtl_power not found',
            hint='pacman -S rtl-sdr') from exc

    try:
        out, _ = await asyncio.wait_for(
            proc.communicate(), timeout=integration * 4 + 20)
    except asyncio.TimeoutError:
        proc.kill()
        raise NotAvailableError('scan timed out')

    signals = find_signals(parse_power_csv(out.decode(errors='replace')),
                           threshold=threshold)

    # Carry preset names through so a scan list reads like a station
    # list rather than a column of numbers.
    for signal in signals:
        preset = find_preset(signal.frequency)
        if preset:
            signal.name = preset.name

    save_scan(signals)

    if resume and previous.playing and previous.frequency is not None:
        await play(previous.frequency, gain=previous.gain)

    return signals


async def known_signals(max_age: float = SCAN_CACHE_SECONDS,
                        **scan_kwargs) -> list[Signal]:
    """
    Cached scan results, sweeping first if they are stale or absent.

    Seeking should not re-sweep on every press -- that would stop the
    audio each time.
    """
    signals, taken = load_scan()
    if signals and (time.time() - taken) < max_age:
        return signals
    return await scan(**scan_kwargs)


async def seek(direction: int = 1,
               max_age: float = SCAN_CACHE_SECONDS) -> RadioState:
    """
    Tune to the next station up or down the band, wrapping around.

    Unlike `next_preset`, this uses what is actually on the air rather
    than what you saved earlier -- which is what you want in a moving
    car.
    """
    signals = await known_signals(max_age=max_age)
    if not signals:
        raise NotFoundError('station', 'any', [])

    current = await status()
    frequencies = [s.frequency for s in signals]

    if not current.playing or current.frequency is None:
        return await play(frequencies[0])

    here = current.frequency

    if direction >= 0:
        nxt = next((f for f in frequencies if f > here + 0.05),
                   frequencies[0])
    else:
        lower = [f for f in frequencies if f < here - 0.05]
        nxt = lower[-1] if lower else frequencies[-1]

    data = _read_state()
    return await play(nxt, gain=current.gain,
                      rds=data.get('rds_enabled', True))


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
    data = _read_state()
    return await play(frequency, gain=current.gain,
                      rds=data.get('rds_enabled', True))


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

    data = _read_state()
    return await play(presets[(index + step) % len(presets)],
                      gain=current.gain,
                      rds=data.get('rds_enabled', True))
