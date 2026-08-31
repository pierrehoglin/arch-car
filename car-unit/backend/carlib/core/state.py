"""
Runtime state.

State that describes what is happening right now -- the radio's pid,
which source was playing, a cached PipeWire node id -- as opposed to
settings, which describe what the user wants and belong in a config
file.

Two backends. Files under XDG_RUNTIME_DIR are the default, so a CLI
invocation can see what a previous one left behind. A long-running
process calls `use_memory()` at startup and keeps everything in
itself.

The distinction matters because the file backend has a real flaw: a
read-modify-write from two processes loses updates. That is not
theoretical -- it cost us a traffic-announcement timeout that never
expired, because the source supervisor kept rewriting a timestamp the
traffic logic had just read. With one process owning the state the
problem disappears, which is the main reason for moving to a daemon at
all.

Namespaces map to files:

    fm        -> $XDG_RUNTIME_DIR/carlib-fm.json
    fm-scan   -> $XDG_RUNTIME_DIR/carlib-fm-scan.json
    source    -> $XDG_RUNTIME_DIR/carlib-source.json
"""

import os
import json
from pathlib import Path
from typing import Any

FILE_PREFIX = 'carlib-'

_memory: dict[str, dict] = {}
_use_memory = False


def _runtime_dir() -> Path:
    base = os.environ.get('XDG_RUNTIME_DIR')
    return Path(base) if base else Path('/tmp')


def path(namespace: str) -> Path:
    """Where a namespace lives when backed by a file."""
    return _runtime_dir() / f'{FILE_PREFIX}{namespace}.json'


# --- Backend selection -----------------------------------------------------

def use_memory() -> None:
    """
    Keep state in this process rather than on disk.

    For a daemon that owns the state and serves everything else over
    an API. Anything still reading the files -- a stray CLI, say --
    will see whatever was there before the switch, which is why the
    CLIs must talk to the daemon rather than the library once this is
    in use.
    """
    global _use_memory
    _use_memory = True


def use_files() -> None:
    """Back to per-invocation files. The default."""
    global _use_memory
    _use_memory = False


def in_memory() -> bool:
    return _use_memory


def reset() -> None:
    """Drop everything held in memory. Mainly for tests."""
    _memory.clear()


# --- Access ----------------------------------------------------------------

def read(namespace: str) -> dict:
    """Everything in a namespace. An absent namespace reads as {}."""
    if _use_memory:
        return dict(_memory.get(namespace, {}))

    target = path(namespace)
    if not target.exists():
        return {}
    try:
        data = json.loads(target.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def write(namespace: str, data: dict) -> None:
    """Replace a namespace wholesale."""
    if _use_memory:
        _memory[namespace] = dict(data)
        return

    try:
        path(namespace).write_text(json.dumps(data))
    except OSError:
        pass


def update(namespace: str, **changes: Any) -> dict:
    """
    Change some keys, leaving the rest alone.

    Prefer this over read-then-write. In memory it is a single
    operation with no window for another writer; with files it at
    least keeps the read and the write adjacent rather than separated
    by whatever the caller does in between.

    Passing None as a value removes the key.
    """
    data = read(namespace)
    for key, value in changes.items():
        if value is None:
            data.pop(key, None)
        else:
            data[key] = value
    write(namespace, data)
    return data


def get(namespace: str, key: str, default: Any = None) -> Any:
    return read(namespace).get(key, default)


def clear(namespace: str) -> None:
    """Remove a namespace entirely."""
    if _use_memory:
        _memory.pop(namespace, None)
        return

    try:
        path(namespace).unlink()
    except OSError:
        pass
