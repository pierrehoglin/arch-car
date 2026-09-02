"""
User settings.

A single JSON file under XDG_CONFIG_HOME, accessed with dot notation:

    from carlib.core import settings

    gain = settings.get('fm.gain', 40)
    settings.set('fm.gain', 42)

Writes are atomic -- a temporary file in the same directory, then
os.replace(). That matters more here than in most projects: a car unit
loses power when the ignition goes off, and a settings file truncated
mid-write would take the whole thing down on next boot. os.replace()
is atomic on POSIX, so a reader sees either the old file or the new
one, never a partial.

A corrupt file is backed up rather than deleted, and defaults are used
until it is fixed. Losing settings is annoying; losing them silently
and having no idea what they were is worse.
"""

import os
import json
import shutil
import tempfile
from pathlib import Path
from dataclasses import dataclass
from typing import Any

CONFIG_DIR = (
    Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config'))
    / 'carlib'
)
SETTINGS_FILE = CONFIG_DIR / 'settings.json'

# Settings may hold a passphrase or an API token, so keep them to the
# owner rather than the default umask.
FILE_MODE = 0o600

_cache: dict | None = None
_cache_mtime: float | None = None


# --- Storage ---------------------------------------------------------------

def _load_file() -> dict:
    if not SETTINGS_FILE.exists():
        return {}

    try:
        text = SETTINGS_FILE.read_text(encoding='utf-8')
    except OSError:
        return {}

    if not text.strip():
        return {}

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # Keep the broken file so its contents can be recovered by
        # hand, and carry on with defaults rather than refusing to
        # start.
        try:
            backup = SETTINGS_FILE.with_suffix('.json.corrupt')
            shutil.copy2(SETTINGS_FILE, backup)
        except OSError:
            pass
        return {}

    return data if isinstance(data, dict) else {}


def _write_file(data: dict) -> None:
    """
    Write atomically.

    The temporary file must be in the same directory as the target:
    os.replace() is only atomic within a filesystem, and /tmp is often
    a different one.
    """
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    handle = tempfile.NamedTemporaryFile(
        mode='w', encoding='utf-8', dir=CONFIG_DIR,
        prefix='.settings-', suffix='.tmp', delete=False)

    try:
        with handle:
            json.dump(data, handle, indent=2, ensure_ascii=False,
                      sort_keys=True)
            handle.write('\n')
            handle.flush()
            # Without the fsync the rename can land before the data
            # does, which on power loss leaves an empty file.
            os.fsync(handle.fileno())

        os.chmod(handle.name, FILE_MODE)
        os.replace(handle.name, SETTINGS_FILE)
    except OSError:
        try:
            os.unlink(handle.name)
        except OSError:
            pass
        raise


def load(force: bool = False) -> dict:
    """
    Everything, as a nested dict.

    Cached, but the cache is invalidated when the file changes on disk
    so separate processes -- a CLI and a status bar, say -- see each
    other's writes.
    """
    global _cache, _cache_mtime

    try:
        mtime = SETTINGS_FILE.stat().st_mtime
    except OSError:
        mtime = None

    if not force and _cache is not None and mtime == _cache_mtime:
        return _cache

    _cache = _load_file()
    _cache_mtime = mtime
    return _cache


def save(data: dict) -> None:
    """Replace the whole file."""
    global _cache, _cache_mtime
    _write_file(data)
    _cache = data
    try:
        _cache_mtime = SETTINGS_FILE.stat().st_mtime
    except OSError:
        _cache_mtime = None


def reload() -> dict:
    """Drop the cache and re-read."""
    return load(force=True)


# --- Dot-notation access ---------------------------------------------------

def _split(key: str) -> list[str]:
    parts = [p for p in str(key).split('.') if p]
    if not parts:
        raise ValueError('empty settings key')
    return parts


def get(key: str, default: Any = None) -> Any:
    """
    Read a value by dotted path.

        settings.get('fm.gain', 40)
        settings.get('display.brightness', 80)

    Returns the default when any part of the path is missing, so
    callers do not have to check each level.
    """
    node: Any = load()
    for part in _split(key):
        if not isinstance(node, dict) or part not in node:
            return default
        node = node[part]
    return node


def set(key: str, value: Any) -> Any:
    """
    Write a value by dotted path, creating intermediate sections.

    Returns the value, so it composes:

        gain = settings.set('fm.gain', 42)
    """
    data = json.loads(json.dumps(load()))     # deep copy
    parts = _split(key)

    node = data
    for part in parts[:-1]:
        existing = node.get(part)
        if not isinstance(existing, dict):
            # A scalar where a section is needed gets replaced. The
            # alternative is raising, which makes changing the shape of
            # your settings unnecessarily painful.
            existing = {}
            node[part] = existing
        node = existing

    node[parts[-1]] = value
    save(data)
    return value


def delete(key: str) -> bool:
    """Remove a key. Returns whether it was there."""
    data = json.loads(json.dumps(load()))
    parts = _split(key)

    node = data
    for part in parts[:-1]:
        node = node.get(part)
        if not isinstance(node, dict):
            return False

    if parts[-1] not in node:
        return False

    del node[parts[-1]]
    save(data)
    return True


def has(key: str) -> bool:
    sentinel = object()
    return get(key, sentinel) is not sentinel


def update(values: dict) -> None:
    """
    Set several keys at once, in one write.

        settings.update({'fm.gain': 42, 'fm.rds': True})

    Cheaper than repeated set() calls, and leaves no window where only
    half the change is on disk.
    """
    data = json.loads(json.dumps(load()))

    for key, value in values.items():
        parts = _split(key)
        node = data
        for part in parts[:-1]:
            existing = node.get(part)
            if not isinstance(existing, dict):
                existing = {}
                node[part] = existing
            node = existing
        node[parts[-1]] = value

    save(data)


# --- Typed reads -----------------------------------------------------------
#
# Settings arrive from a config file a human may have edited, so a
# value can be the wrong type. These coerce where it is sensible and
# fall back to the default where it is not, rather than raising in the
# middle of unrelated code.

def get_int(key: str, default: int = 0) -> int:
    value = get(key, default)
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def get_float(key: str, default: float = 0.0) -> float:
    value = get(key, default)
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def get_bool(key: str, default: bool = False) -> bool:
    value = get(key, default)
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in ('true', 'yes', 'on', '1'):
            return True
        if lowered in ('false', 'no', 'off', '0'):
            return False
    return default


def get_str(key: str, default: str = '') -> str:
    value = get(key, default)
    return default if value is None else str(value)


def get_list(key: str, default: list | None = None) -> list:
    value = get(key, default)
    if isinstance(value, list):
        return value
    return list(default or [])


def get_dict(key: str, default: dict | None = None) -> dict:
    value = get(key, default)
    if isinstance(value, dict):
        return value
    return dict(default or {})


# --- Catalogue -------------------------------------------------------------
#
# What settings exist, so they can be discovered without reading the
# source. This is documentation, not validation: an undeclared key
# still works, and a declared one is not created until something sets
# it.
#
# Kept centrally rather than declared by each module. Per-module
# declarations would mean importing every module to list them, and
# import side-effects to power a help command is a poor trade.


@dataclass(frozen=True)
class Known:
    key: str
    default: Any
    description: str
    kind: str = 'str'


CATALOGUE: tuple[Known, ...] = (
    Known('contact', '', 'Email or URL identifying this unit to '
          'external services. Some weather providers block requests '
          'they cannot attribute.'),

    Known('fm.autostart', False, 'Start the radio when the daemon '
          'starts.', 'bool'),
    Known('fm.gain', 40.0, 'Tuner gain in dB. A bare wire wants ~40; '
          'a car antenna usually less.', 'float'),
    Known('fm.rds', True, 'Decode RDS. Off costs less CPU but loses '
          'station names and traffic announcements.', 'bool'),
    Known('fm.traffic', True, 'Let traffic announcements interrupt '
          'whatever is playing.', 'bool'),
    Known('fm.presets', [], 'Saved stations. Managed by `fm save` and '
          '`fm forget`.', 'list'),
    Known('fm.last', {}, 'The station playing when the radio last '
          'stopped, so it resumes there.', 'dict'),

    Known('weather.provider', 'metno', 'Which weather service to use. '
          'See `weather providers`.'),
    Known('weather.contact', '', 'Overrides `contact` for weather '
          'services only.'),
    Known('weather.openweather.key', '', 'OpenWeather API key, from '
          'home.openweathermap.org/api_keys. Needed only if '
          'weather.provider is openweather.'),
    Known('places', [], 'Named locations, shared by anything that '
          'needs one. Managed by `places save` and `places forget`.',
          'list'),
    Known('location.latitude', None, 'Pin "here" to a latitude '
          'instead of using GPS. Set with location.longitude.',
          'float'),
    Known('location.longitude', None, 'Pin "here" to a longitude '
          'instead of using GPS.', 'float'),
    Known('location.altitude', None, 'Altitude in metres for the '
          'pinned position.', 'float'),

    Known('geocoding.auto', False, 'Look up the current address as '
          'the car moves. Uses Nominatim, whose usage policy applies: '
          'operations.osmfoundation.org/policies/nominatim/', 'bool'),
    Known('geocoding.move_metres', 1000.0, 'How far to move before '
          'looking up the address again. Lower is fine -- the 4 per '
          'minute ceiling is enforced separately.', 'float'),
    Known('geocoding.min_move_metres', 50.0, 'Shortest move that can '
          'trigger a lookup once the address has gone stale.',
          'float'),
    Known('geocoding.stale_seconds', 120.0, 'After this, a short move '
          'is enough to look the address up again.', 'float'),
)

_BY_KEY = {entry.key: entry for entry in CATALOGUE}


def known(key: str) -> Known | None:
    return _BY_KEY.get(key)


def catalogue() -> list[Known]:
    return sorted(CATALOGUE, key=lambda e: e.key)


def declared_keys() -> frozenset:
    # Annotated as frozenset because this module defines its own
    # set(), which shadows the builtin in annotations.
    return frozenset(_BY_KEY)


# --- Sections --------------------------------------------------------------

class Section:
    """
    A view onto one part of the settings.

        fm = settings.section('fm')
        fm.get('gain', 40)
        fm.set('gain', 42)

    Modules should take a section rather than reaching for dotted paths
    directly, so the prefix lives in one place.
    """

    def __init__(self, prefix: str):
        self.prefix = prefix.rstrip('.')

    def _key(self, key: str) -> str:
        return f'{self.prefix}.{key}' if key else self.prefix

    def get(self, key: str, default: Any = None) -> Any:
        return get(self._key(key), default)

    def set(self, key: str, value: Any) -> Any:
        return set(self._key(key), value)

    def delete(self, key: str) -> bool:
        return delete(self._key(key))

    def has(self, key: str) -> bool:
        return has(self._key(key))

    def update(self, values: dict) -> None:
        update({self._key(k): v for k, v in values.items()})

    def all(self) -> dict:
        return get_dict(self.prefix, {})

    def get_int(self, key: str, default: int = 0) -> int:
        return get_int(self._key(key), default)

    def get_float(self, key: str, default: float = 0.0) -> float:
        return get_float(self._key(key), default)

    def get_bool(self, key: str, default: bool = False) -> bool:
        return get_bool(self._key(key), default)

    def get_str(self, key: str, default: str = '') -> str:
        return get_str(self._key(key), default)

    def get_list(self, key: str, default: list | None = None) -> list:
        return get_list(self._key(key), default)

    def get_dict(self, key: str, default: dict | None = None) -> dict:
        return get_dict(self._key(key), default)


def section(prefix: str) -> Section:
    return Section(prefix)


def path() -> Path:
    """Where the settings file lives, for messages and editors."""
    return SETTINGS_FILE
