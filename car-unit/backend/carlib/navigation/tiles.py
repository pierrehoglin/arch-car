"""
The offline map, as stored on disk and served to the screens.

Two parts, kept separately because they change separately:

    tiles    one PMTiles archive of Sweden -- every road, building and
             name, as vector tiles. The browser reads it with HTTP
             range requests, a few kilobytes at a time, so the daemon
             does nothing cleverer than serve the file. Starlette's
             FileResponse answers ranges itself.

    labels   the fonts the names are drawn with and the icon sheets
             (one-way arrows, road shields, places). Without them the
             map still draws, but with no text on it.

Both are fetched by carlib.navigation.download. This module only knows
where they live and what is there; it never touches the network.

    ~/.local/share/carlib/maps/
        sweden.pmtiles                  the tiles (or map.tiles)
        installed.json                  what was installed, and when
        assets/fonts/<stack>/<a>-<b>.pbf
        assets/sprites/<flavour>[@2x].{json,png}
"""

import os
import re
import json
import time
import tempfile
from pathlib import Path

from carlib.core import settings
from carlib.core.errors import NotAvailableError, NotFoundError


def data_dir() -> Path:
    base = os.environ.get('XDG_DATA_HOME')
    root = Path(base) if base else Path.home() / '.local' / 'share'
    return root / 'carlib' / 'maps'


DEFAULT_FILE = data_dir() / 'sweden.pmtiles'
ASSETS_DIR = data_dir() / 'assets'
META_FILE = data_dir() / 'installed.json'

# The area the archive covers and the screens keep the map within, as
# west, south, east, north. Sweden with a margin.
BOUNDS = (10.5, 55.0, 24.2, 69.1)

HINT = ('No map yet. Download one from Settings > Map, or put a '
        f'PMTiles archive at {DEFAULT_FILE}.')

# What a font or sprite request may name. Checked before touching the
# disk: these come straight from a URL.
FONT_RANGE = re.compile(r'^\d{1,5}-\d{1,5}$')
SPRITE_NAME = re.compile(r'^[a-z]+(@2x)?\.(json|png)$')


def path() -> Path:
    """Where the archive is expected, whether or not it is there."""
    configured = settings.get_str('map.tiles', '')
    return Path(configured).expanduser() if configured else DEFAULT_FILE


# --- What is installed ------------------------------------------------------

def read_meta() -> dict:
    try:
        data = json.loads(META_FILE.read_text())
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def write_meta(section: str, values: dict) -> None:
    """Record one part as installed. Atomic, like the settings file."""
    data = read_meta()
    data[section] = {**values, 'installed': time.time()}

    META_FILE.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        'w', dir=META_FILE.parent, prefix='.installed-', suffix='.tmp',
        delete=False)
    with handle:
        json.dump(data, handle, indent=2)
    os.replace(handle.name, META_FILE)


def _tree_size(root: Path) -> int:
    return sum(f.stat().st_size for f in root.rglob('*') if f.is_file())


def labels_available() -> bool:
    """Fonts and sprites both present. Either alone is no use."""
    return ((ASSETS_DIR / 'fonts').is_dir()
            and (ASSETS_DIR / 'sprites').is_dir())


def status() -> dict:
    """What there is on disk. No network."""
    target = path()
    present = target.is_file()
    meta = read_meta()
    tiles_meta = meta.get('tiles', {}) if present else {}
    labels_meta = meta.get('labels', {})
    labels = labels_available()

    return {
        'available': present,
        'path': str(target),
        'size_bytes': target.stat().st_size if present else 0,
        'bounds': list(BOUNDS),
        'hint': '' if present else HINT,
        # Empty for an archive put there by hand.
        'build': tiles_meta.get('build', ''),
        'maxzoom': tiles_meta.get('maxzoom'),
        'installed': tiles_meta.get('installed'),
        'labels': {
            'available': labels,
            'size_bytes': labels_meta.get('size_bytes', 0) if labels else 0,
            'installed': labels_meta.get('installed') if labels else None,
        },
    }


# --- Serving ---------------------------------------------------------------

def archive() -> Path:
    """The archive to serve. Raises with a way forward if it is missing."""
    target = path()
    if not target.is_file():
        raise NotAvailableError(f'no map at {target}', hint=HINT)
    return target


def font(stack: str, span: str) -> Path:
    """One glyph range of one font, e.g. ('Noto Sans Regular', '0-255')."""
    if '/' in stack or '..' in stack or not FONT_RANGE.match(span):
        raise NotFoundError('font', f'{stack}/{span}', [])
    target = ASSETS_DIR / 'fonts' / stack / f'{span}.pbf'
    if not target.is_file():
        raise NotFoundError('font', f'{stack}/{span}', [])
    return target


def sprite(name: str) -> Path:
    """An icon sheet or its index, e.g. 'dark@2x.png'."""
    if not SPRITE_NAME.match(name):
        raise NotFoundError('sprite', name, [])
    target = ASSETS_DIR / 'sprites' / name
    if not target.is_file():
        raise NotFoundError('sprite', name, [])
    return target
