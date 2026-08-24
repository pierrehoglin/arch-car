"""
Shared CLI plumbing.

Kept out of the domain modules so the library stays free of printing and
process exits -- an HTTP handler importing carlib.bluetooth.calls
should not drag in argparse or sys.exit.
"""

import sys
import json
import asyncio
from dataclasses import is_dataclass, asdict
from typing import Any, Awaitable

from carlib.core.errors import (
    CarError,
    NotFoundError,
    AmbiguousMatchError,
    NotAvailableError,
    TransferError,
)

# Nerd Font glyphs. Empty boxes mean the font is missing --
# `pacman -S ttf-nerd-fonts-symbols`.
GLYPH = {
    'bluetooth':   '\U000f00af',
    'play':        '\U000f040a',
    'pause':       '\U000f03e4',
    'stop':        '\U000f04db',
    'phone':       '\U000f011c',
    'incoming':    '\U000f0b6f',
    'outgoing':    '\U000f0b74',
    'missed':      '\U000f0b71',
    'headset':     '\U000f02cb',
    'speaker':     '\U000f075a',
    'keyboard':    '\U000f030c',
    'mouse':       '\U000f037d',
    'computer':    '\U000f0379',
    'controller':  '\U000f0eb5',
    'watch':       '\U000f0b56',
    'car':         '\U000f010b',
}

DEVICE_ICONS = {
    'audio-card':        GLYPH['speaker'],
    'audio-headset':     GLYPH['headset'],
    'audio-headphones':  GLYPH['headset'],
    'computer':          GLYPH['computer'],
    'input-gaming':      GLYPH['controller'],
    'input-keyboard':    GLYPH['keyboard'],
    'input-mouse':       GLYPH['mouse'],
    'multimedia-player': GLYPH['speaker'],
    'phone':             GLYPH['phone'],
}

STATUS_GLYPH = {
    'playing': GLYPH['play'],
    'paused':  GLYPH['pause'],
    'stopped': GLYPH['stop'],
}

CALL_GLYPH = {
    'received': GLYPH['incoming'],
    'dialed':   GLYPH['outgoing'],
    'missed':   GLYPH['missed'],
}


def to_jsonable(value: Any) -> Any:
    """Dataclasses, lists of them, and plain data alike."""
    if is_dataclass(value) and not isinstance(value, type):
        return asdict(value)
    if isinstance(value, (list, tuple)):
        return [to_jsonable(v) for v in value]
    if isinstance(value, dict):
        return {k: to_jsonable(v) for k, v in value.items()}
    return value


def emit_json(value: Any) -> None:
    print(json.dumps(to_jsonable(value), indent=2, ensure_ascii=False))


def run(coro: Awaitable[Any]) -> int:
    """
    Run a coroutine and turn library exceptions into exit codes.

    Exit codes mirror the exception hierarchy so shell scripts can
    branch on them:
        2  not found        3  ambiguous
        4  not available    5  transfer failed
        1  other            130 interrupted
    """
    try:
        asyncio.run(coro)
    except KeyboardInterrupt:
        return 130
    except NotFoundError as exc:
        print(f'error: {exc}', file=sys.stderr)
        return 2
    except AmbiguousMatchError as exc:
        print(f'error: {exc}', file=sys.stderr)
        return 3
    except NotAvailableError as exc:
        print(f'error: {exc}', file=sys.stderr)
        return 4
    except TransferError as exc:
        print(f'error: {exc}', file=sys.stderr)
        return 5
    except CarError as exc:
        print(f'error: {exc}', file=sys.stderr)
        return 1
    except Exception as exc:
        print(f'error: {exc}', file=sys.stderr)
        return 1
    return 0


def add_target(parser, name: str = 'target', required: bool = True,
               help_text: str = 'MAC, path fragment or name'):
    """
    Add the device selector.

    Optional when a single phone is connected, which is the common case
    in a car -- the library falls back to the only candidate.
    """
    if required:
        parser.add_argument(name, metavar='MAC|NAME', help=help_text)
    else:
        parser.add_argument(name, metavar='MAC|NAME', nargs='?',
                            default=None, help=help_text + ' (optional)')
    return parser


def dash(value, suffix: str = '') -> str:
    """Render None as a dash, otherwise the value plus an optional unit."""
    if value is None or value == '':
        return '-'
    return f'{value}{suffix}'


def column_width(items, attr: str, minimum: int = 10) -> int:
    values = [getattr(i, attr, '') or '' for i in items]
    return max([len(v) for v in values] + [minimum])
