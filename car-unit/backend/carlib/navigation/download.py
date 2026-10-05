"""
Fetching the offline map: the tiles and the labels.

Tiles are cut out of the Protomaps planet build -- about 140 GB, one
new build a day -- with the `pmtiles` tool, which reads only the part
of the planet inside Sweden's box over HTTP range requests. The
download is roughly the size of the result, not of the planet.

    builds.json     lists the daily builds; the newest is taken
    pmtiles extract <build> sweden.partial --bbox ... --maxzoom N
                    then renamed over the old file, so the map keeps
                    working until the new one is complete

Labels are the fonts and icon sheets the map style draws names and
symbols with. Without them a map still draws, but blank. They come
from the Protomaps assets site file by file: three fonts of 256 glyph
ranges each, plus the icon sheets for the light and dark styles.

One job at a time, tiles or labels. Progress is reported through
`on_change`, which the daemon points at the event stream.

Requires the `pmtiles` tool for tiles (labels need nothing):
    https://github.com/protomaps/go-pmtiles/releases
    -- the Linux_arm64 archive on the Pi, into ~/.local/bin
"""

import os
import re
import time
import shutil
import signal
import asyncio
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Callable

from carlib.core import settings
from carlib.core.errors import NotAvailableError
from carlib.navigation import tiles

BUILDS_URL = 'https://build-metadata.protomaps.dev/builds.json'
BUILD_URL = 'https://build.protomaps.com/{key}'
ASSETS_URL = 'https://protomaps.github.io/basemaps-assets'

# The tile schema the map style understands. @protomaps/basemaps 5
# draws schema 4 tiles; a build of a later major version would load
# and then draw wrongly, so it is not offered until the frontend is
# updated to match.
SCHEMA_MAJOR = 4

# What the style asks for, with Swedish labels. Devanagari is in the
# assets too, but only used for languages written in it.
FONT_STACKS = ('Noto Sans Regular', 'Noto Sans Medium', 'Noto Sans Italic')
GLYPH_RANGES = 256
SPRITES = ('light', 'dark')
SPRITE_FILES = ('.json', '.png', '@2x.json', '@2x.png')

PMTILES = 'pmtiles'
DOWNLOAD_THREADS = 4
LABEL_CONCURRENCY = 8

# Detail levels offered. Each zoom level roughly doubles the size;
# beyond the archive's last level MapLibre stretches the vectors,
# which stays sharp, so a lower level mostly loses small detail --
# house numbers, footpaths, building outlines -- when zoomed right in.
DETAIL = (12, 13, 14, 15)
DEFAULT_MAXZOOM = 15

# Room to leave on the card beyond the download itself.
DISK_MARGIN = 200 * 1000 * 1000

# How often progress is published while bytes are arriving.
REPORT_INTERVAL = 0.5

# A download that has not moved for this long is given up on. A link
# that stays up while nothing arrives -- a tunnel, a cell that has
# stopped routing -- would otherwise hold the job at the same
# percentage until someone noticed and pressed Cancel. Generous,
# because reading the build's index before the first tile can take a
# minute on a slow link and shows no progress while it does.
STALL_SECONDS = 180.0

# How often the stall is checked while pmtiles is silent.
WATCH_INTERVAL = 10.0

LATEST_TTL = 3600.0


def pmtiles_tool() -> str | None:
    configured = settings.get_str('map.pmtiles', '')
    if configured:
        return configured if Path(configured).is_file() else None
    found = shutil.which(PMTILES)
    if found:
        return found
    local = Path.home() / '.local' / 'bin' / PMTILES
    return str(local) if local.is_file() else None


TOOL_HINT = ('Map downloads need the pmtiles tool: download the '
             'Linux_arm64 archive from github.com/protomaps/go-pmtiles/'
             'releases and put `pmtiles` in ~/.local/bin.')


def default_maxzoom() -> int:
    value = settings.get_int('map.maxzoom', DEFAULT_MAXZOOM)
    return value if value in DETAIL else DEFAULT_MAXZOOM


# --- Sizes -----------------------------------------------------------------

UNITS = {'b': 1, 'kb': 1e3, 'mb': 1e6, 'gb': 1e9, 'tb': 1e12,
         'kib': 1024, 'mib': 1024 ** 2, 'gib': 1024 ** 3}


def parse_size(text: str) -> int:
    """'2.5 kB' -> 2500. pmtiles prints SI units."""
    matched = re.match(r'\s*([\d.]+)\s*([a-zA-Z]+)', text)
    if not matched:
        return 0
    unit = UNITS.get(matched.group(2).lower())
    return int(float(matched.group(1)) * unit) if unit else 0


def parse_estimate(output: str) -> int:
    """The archive size from a dry run's last lines."""
    matched = re.search(r'archive size of ([\d.]+\s*[a-zA-Z]+)', output)
    return parse_size(matched.group(1)) if matched else 0


# Progress lines look like
#   fetching chunks  42% |████     | (580 MB/1.4 GB, 9.1 MB/s) [1m4s:1m30s]
PROGRESS = re.compile(r'(\d{1,3})%\s*\|.*?\(([^)]*)\)')


def parse_progress(line: str) -> tuple[float, str] | None:
    matched = PROGRESS.search(line)
    if not matched:
        return None
    return float(matched.group(1)), matched.group(2).strip()


# --- The job ---------------------------------------------------------------

@dataclass
class Job:
    """One download, as the settings screen shows it."""

    kind: str                   # tiles | labels
    # starting -> checking -> downloading -> installing -> done
    # or failed / cancelled from any of them
    phase: str = 'starting'
    percent: float = 0.0
    detail: str = ''            # "580 MB/1.4 GB, 9.1 MB/s", "312 of 776"
    build: str = ''             # 2026-10-05
    maxzoom: int | None = None
    expected_bytes: int = 0
    started: float = field(default_factory=time.time)
    finished: float | None = None
    error: str = ''

    @property
    def active(self) -> bool:
        return self.phase not in ('done', 'failed', 'cancelled')

    def to_dict(self) -> dict:
        return asdict(self)


_job: Job | None = None
_task: asyncio.Task | None = None
_proc: asyncio.subprocess.Process | None = None
_last_report = 0.0

_latest: dict | None = None
_latest_at = 0.0
_estimates: dict[tuple[str, int], int] = {}

# Set by the daemon. Called with no arguments when anything changes;
# whoever listens reads status().
on_change: Callable[[], None] | None = None


def _changed(force: bool = True) -> None:
    global _last_report
    now = time.monotonic()
    if not force and now - _last_report < REPORT_INTERVAL:
        return
    _last_report = now
    if on_change:
        try:
            on_change()
        except Exception:
            pass


def status() -> dict:
    """What is installed, what is newest, and what is running."""
    tool = pmtiles_tool()
    return {
        **tiles.status(),
        'tool': {'available': tool is not None,
                 'hint': '' if tool else TOOL_HINT},
        'latest': _latest,
        'detail_levels': list(DETAIL),
        'maxzoom_setting': default_maxzoom(),
        'job': _job.to_dict() if _job else None,
    }


# --- Builds ----------------------------------------------------------------

async def _client():
    try:
        import httpx
    except ImportError as exc:
        raise NotAvailableError('httpx is not installed',
                                hint='uv sync') from exc
    return httpx


async def latest(refresh: bool = False) -> dict:
    """The newest planet build this map style can draw."""
    global _latest, _latest_at

    if (not refresh and _latest
            and time.monotonic() - _latest_at < LATEST_TTL):
        return _latest

    httpx = await _client()
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(BUILDS_URL)
            response.raise_for_status()
            builds = response.json()
    except Exception as exc:
        raise NotAvailableError(
            f'cannot reach the map build list: {exc}',
            hint='the car needs internet to download maps') from exc

    usable = []
    for entry in builds if isinstance(builds, list) else []:
        key = str(entry.get('key', ''))
        version = str(entry.get('version', ''))
        if not re.fullmatch(r'\d{8}\.pmtiles', key):
            continue
        if version.split('.')[0] != str(SCHEMA_MAJOR):
            continue
        usable.append(entry)

    if not usable:
        raise NotAvailableError('no usable map build listed')

    newest = max(usable, key=lambda e: e['key'])
    day = newest['key'][:8]
    _latest = {
        'key': newest['key'],
        'build': f'{day[:4]}-{day[4:6]}-{day[6:]}',
        'version': newest.get('version', ''),
        'planet_bytes': newest.get('size', 0),
    }
    _latest_at = time.monotonic()
    return _latest


def _extract_args(tool: str, key: str, output: str, maxzoom: int,
                  dry_run: bool = False) -> list[str]:
    west, south, east, north = tiles.BOUNDS
    args = [tool, 'extract', BUILD_URL.format(key=key), output,
            f'--bbox={west},{south},{east},{north}',
            f'--maxzoom={maxzoom}',
            f'--download-threads={DOWNLOAD_THREADS}']
    if dry_run:
        args.append('--dry-run')
    return args


async def estimate(maxzoom: int) -> dict:
    """
    How big Sweden is at this detail, from a dry run.

    The dry run reads the build's index -- a few megabytes -- but no
    tiles, so it takes seconds rather than the minutes a download
    does. Remembered per build and level.
    """
    if maxzoom not in DETAIL:
        raise NotAvailableError(f'detail must be one of {DETAIL}')

    tool = pmtiles_tool()
    if not tool:
        raise NotAvailableError('pmtiles not found', hint=TOOL_HINT)

    build = await latest()
    cached = _estimates.get((build['key'], maxzoom))
    if cached is not None:
        return {'maxzoom': maxzoom, 'bytes': cached,
                'build': build['build']}

    proc = await asyncio.create_subprocess_exec(
        *_extract_args(tool, build['key'], os.devnull, maxzoom, True),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT)
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=120)
    except asyncio.TimeoutError:
        proc.kill()
        raise NotAvailableError('the size check timed out')

    size = parse_estimate(out.decode(errors='replace'))
    if proc.returncode != 0 or not size:
        tail = out.decode(errors='replace').strip().splitlines()[-1:]
        raise NotAvailableError(
            'could not work out the size',
            hint=tail[0] if tail else None)

    _estimates[(build['key'], maxzoom)] = size
    return {'maxzoom': maxzoom, 'bytes': size, 'build': build['build']}


# --- Running jobs ----------------------------------------------------------

def partial_files() -> list[Path]:
    """What an interrupted download leaves behind."""
    target = tiles.path()
    return [
        target.with_name(target.name + '.partial'),
        tiles.ASSETS_DIR.with_name('assets.partial'),
        tiles.ASSETS_DIR.with_name('assets.old'),
    ]


def cleanup() -> list[str]:
    """
    Remove what an interrupted download left behind.

    A download that fails or is cancelled tidies up after itself, but
    one cut off by the daemon stopping -- the ignition going off --
    does not, and a half-downloaded map can be gigabytes sitting on the
    card, counted against the free-space check. Called when the daemon
    starts, before anything could be downloading.

    assets.old is only ever there for the instant of a label swap; one
    left over means the new set is already in place.
    """
    if _job and _job.active:
        return []

    removed = []
    for leftover in partial_files():
        if leftover.is_dir():
            shutil.rmtree(leftover, ignore_errors=True)
        elif leftover.exists():
            leftover.unlink(missing_ok=True)
        else:
            continue
        removed.append(str(leftover))
    return removed


def _begin(kind: str) -> Job:
    global _job
    if _job and _job.active:
        raise NotAvailableError(
            f'a {_job.kind} download is already running',
            hint='wait for it, or cancel it first')
    _job = Job(kind=kind)
    _changed()
    return _job


def _finish(job: Job, phase: str, error: str = '') -> None:
    job.phase = phase
    job.error = error
    job.finished = time.time()
    _changed()


def start_tiles(maxzoom: int | None = None) -> Job:
    """Begin downloading the map. Returns at once; follow on_change."""
    global _task
    maxzoom = maxzoom if maxzoom is not None else default_maxzoom()
    if maxzoom not in DETAIL:
        raise NotAvailableError(f'detail must be one of {DETAIL}')
    if not pmtiles_tool():
        raise NotAvailableError('pmtiles not found', hint=TOOL_HINT)

    job = _begin('tiles')
    job.maxzoom = maxzoom
    settings.set('map.maxzoom', maxzoom)
    _task = _launch(job, lambda: _tiles(job))
    return job


def start_labels() -> Job:
    global _task
    job = _begin('labels')
    _task = _launch(job, lambda: _labels(job))
    return job


def _launch(job: Job, work) -> asyncio.Task:
    """Start the job's task. If even that fails -- no running loop --
    the job is marked failed rather than left "starting", which would
    refuse every download after it."""
    try:
        return asyncio.create_task(_run(job, work))
    except Exception as exc:
        _finish(job, 'failed', str(exc))
        raise


async def cancel() -> dict:
    """Stop whatever is running. The installed map is left alone."""
    if _proc and _proc.returncode is None:
        try:
            os.killpg(_proc.pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError, OSError):
            pass
    if _task and not _task.done():
        _task.cancel()
        try:
            await _task
        except (asyncio.CancelledError, Exception):
            pass
    # A task cancelled before it ever ran never reaches _finish, and
    # the job would stay "starting" -- blocking every download after.
    if _job and _job.active:
        _finish(_job, 'cancelled')
    return status()


async def _run(job: Job, work) -> None:
    """Run a job to its end. `work` is called here rather than passed
    in already started, so a job cancelled before its first step
    leaves no coroutine behind that was never awaited."""
    try:
        await work()
        _finish(job, 'done')
    except asyncio.CancelledError:
        _finish(job, 'cancelled')
    except Exception as exc:
        message = str(exc).strip().splitlines()
        _finish(job, 'failed', message[0] if message else type(exc).__name__)


async def _tiles(job: Job) -> None:
    global _proc

    job.phase = 'checking'
    _changed()

    build = await latest(refresh=True)
    job.build = build['build']
    sized = await estimate(job.maxzoom)
    job.expected_bytes = sized['bytes']
    _changed()

    target = tiles.path()
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_name(target.name + '.partial')

    # Gone before measuring the space: a leftover from an earlier
    # attempt is about to be overwritten anyway, so it should not count
    # against this one.
    partial.unlink(missing_ok=True)

    free = shutil.disk_usage(target.parent).free
    if free < job.expected_bytes + DISK_MARGIN:
        raise NotAvailableError(
            f'not enough space: needs {job.expected_bytes // 1_000_000} '
            f'MB, {free // 1_000_000} MB free')

    job.phase = 'downloading'
    _changed()

    tool = pmtiles_tool()
    _proc = await asyncio.create_subprocess_exec(
        *_extract_args(tool, build['key'], str(partial), job.maxzoom),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        start_new_session=True)

    last_line = ''
    buffer = ''
    # What counts as moving: the percentage and the bytes so far. Not
    # the whole progress text, which carries a speed that keeps
    # changing even while nothing arrives.
    moved = None
    moved_at = time.monotonic()
    try:
        while True:
            try:
                chunk = await asyncio.wait_for(
                    _proc.stdout.read(512), timeout=WATCH_INTERVAL)
            except asyncio.TimeoutError:
                chunk = None

            if chunk == b'':
                break

            if chunk:
                buffer += chunk.decode(errors='replace')
                # The progress bar redraws with \r; log lines end in \n.
                *lines, buffer = re.split(r'[\r\n]', buffer)
                for line in lines:
                    if not line.strip():
                        continue
                    last_line = line.strip()
                    progress = parse_progress(line)
                    if progress:
                        job.percent, job.detail = progress
                        _changed(force=False)
                        mark = (job.percent, job.detail.split(',')[0])
                        if mark != moved:
                            moved, moved_at = mark, time.monotonic()

            if time.monotonic() - moved_at > STALL_SECONDS:
                try:
                    os.killpg(_proc.pid, signal.SIGKILL)
                except (ProcessLookupError, PermissionError, OSError):
                    pass
                await _proc.wait()
                partial.unlink(missing_ok=True)
                raise NotAvailableError(
                    f'the download stopped moving at {job.percent:.0f}% '
                    f'for {STALL_SECONDS / 60:.0f} minutes -- the '
                    'connection may have dropped. Try again with signal.')
        code = await _proc.wait()
    except asyncio.CancelledError:
        try:
            os.killpg(_proc.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError, OSError):
            pass
        partial.unlink(missing_ok=True)
        raise
    finally:
        _proc = None

    if code != 0 or not partial.is_file():
        partial.unlink(missing_ok=True)
        raise NotAvailableError(f'pmtiles failed: {last_line}')

    job.phase = 'installing'
    job.percent = 100.0
    _changed()

    # Replaced, not rewritten: the daemon may be serving the old file
    # this moment, and a rename leaves its open handle on the old one
    # until the request ends.
    os.replace(partial, target)
    tiles.write_meta('tiles', {
        'build': job.build,
        'maxzoom': job.maxzoom,
        'size_bytes': target.stat().st_size,
    })


def label_files() -> list[str]:
    """Every file the labels are, relative to the assets site."""
    files = []
    for stack in FONT_STACKS:
        for index in range(GLYPH_RANGES):
            start = index * 256
            files.append(f'fonts/{stack}/{start}-{start + 255}.pbf')
    for flavour in SPRITES:
        for suffix in SPRITE_FILES:
            files.append(f'sprites/v4/{flavour}{suffix}')
    return files


async def _labels(job: Job) -> None:
    httpx = await _client()
    files = label_files()

    staging = tiles.ASSETS_DIR.with_name('assets.partial')
    shutil.rmtree(staging, ignore_errors=True)

    job.phase = 'downloading'
    job.detail = f'0 of {len(files)}'
    _changed()

    done = 0
    total_bytes = 0
    limit = asyncio.Semaphore(LABEL_CONCURRENCY)

    async def fetch(client, relative: str) -> None:
        nonlocal done, total_bytes
        # sprites/v4/dark.json is stored as sprites/dark.json: the
        # version is a property of the download, not of the path the
        # style asks for.
        local = relative.replace('sprites/v4/', 'sprites/')
        destination = staging / local
        destination.parent.mkdir(parents=True, exist_ok=True)

        async with limit:
            for attempt in range(3):
                try:
                    response = await client.get(f'{ASSETS_URL}/{relative}')
                    response.raise_for_status()
                    break
                except Exception:
                    if attempt == 2:
                        raise
                    await asyncio.sleep(1.0 + attempt)

        destination.write_bytes(response.content)
        done += 1
        total_bytes += len(response.content)
        job.percent = round(done * 100 / len(files), 1)
        job.detail = f'{done} of {len(files)}'
        _changed(force=False)

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            await asyncio.gather(*(fetch(client, f) for f in files))
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise

    job.phase = 'installing'
    _changed()

    # Swapped as whole directories, so the map never sees half of an
    # old set and half of a new one.
    old = tiles.ASSETS_DIR.with_name('assets.old')
    shutil.rmtree(old, ignore_errors=True)
    if tiles.ASSETS_DIR.exists():
        os.replace(tiles.ASSETS_DIR, old)
    os.replace(staging, tiles.ASSETS_DIR)
    shutil.rmtree(old, ignore_errors=True)

    tiles.write_meta('labels', {'size_bytes': total_bytes,
                                'files': len(files)})
