"""
The offline map: one PMTiles archive on disk, served to the screens.

PMTiles is a single file holding every vector tile of a region. The
browser reads it with HTTP range requests -- a few kilobytes of index,
then only the tiles in view -- so the daemon does nothing cleverer
than serve the file. Starlette's FileResponse answers ranges itself.

Where the file lives is the `map.tiles` setting. Making it is a step
done once, on any machine with the `pmtiles` CLI (the archive is cut
from the Protomaps planet build, which is too big to download whole):

    pmtiles extract https://build.protomaps.com/<YYYYMMDD>.pmtiles \\
        sweden.pmtiles --bbox=10.5,55.0,24.2,69.1 --maxzoom=15

Builds are listed at https://maps.protomaps.com/builds/. A lower
--maxzoom roughly halves the size per level dropped, at the cost of
detail when zoomed right in; `--dry-run` reports the size first.
"""

import os
from pathlib import Path

from carlib.core import settings
from carlib.core.errors import NotAvailableError


def _data_dir() -> Path:
    base = os.environ.get('XDG_DATA_HOME')
    root = Path(base) if base else Path.home() / '.local' / 'share'
    return root / 'carlib' / 'maps'


DEFAULT_FILE = _data_dir() / 'sweden.pmtiles'

# The area the screens keep the map within, as west, south, east,
# north. Sweden with a margin, matching the extract above -- panning
# off the edge of the archive only shows empty background.
BOUNDS = (10.5, 55.0, 24.2, 69.1)

HINT = (
    'make one with `pmtiles extract https://build.protomaps.com/'
    '<YYYYMMDD>.pmtiles sweden.pmtiles --bbox=10.5,55.0,24.2,69.1 '
    '--maxzoom=15` (builds: https://maps.protomaps.com/builds/), then '
    f'put it at {DEFAULT_FILE} or set map.tiles to where it is'
)


def path() -> Path:
    """Where the archive is expected, whether or not it is there."""
    configured = settings.get_str('map.tiles', '')
    return Path(configured).expanduser() if configured else DEFAULT_FILE


def status() -> dict:
    """Whether there is a map, and how big it is."""
    target = path()
    present = target.is_file()
    return {
        'available': present,
        'path': str(target),
        'size_bytes': target.stat().st_size if present else 0,
        'bounds': list(BOUNDS),
        'hint': '' if present else HINT,
    }


def archive() -> Path:
    """The archive to serve. Raises with a way forward if it is missing."""
    target = path()
    if not target.is_file():
        raise NotAvailableError(f'no map at {target}', hint=HINT)
    return target
