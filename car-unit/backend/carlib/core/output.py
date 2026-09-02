"""
Shared CLI plumbing.

Kept out of the domain modules so the library stays free of printing and
process exits -- an HTTP handler importing carlib.bluetooth.calls
should not drag in argparse or sys.exit.
"""

import sys
import json
import argparse
import asyncio
from enum import Enum
from datetime import date, datetime
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
    """
    Dataclasses, lists of them, and plain data alike.

    A dataclass's own to_dict() wins over asdict(), because several of
    them convert fields json cannot handle -- asdict() recurses into
    nested dataclasses but leaves a datetime as a datetime, which then
    fails at json.dumps with a message that says nothing about which
    field.
    """
    if is_dataclass(value) and not isinstance(value, type):
        converter = getattr(value, 'to_dict', None)
        if callable(converter):
            return to_jsonable(converter())
        return to_jsonable(asdict(value))
    if isinstance(value, (list, tuple)):
        return [to_jsonable(v) for v in value]
    if isinstance(value, dict):
        return {k: to_jsonable(v) for k, v in value.items()}
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
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


def global_flags(*names: str, **flags):
    """
    A parent parser whose flags do not get clobbered by subparsers.

    The trap: a flag defined on a parent and inherited by every
    subparser is parsed twice. `tool --json sub` sets --json on the
    top-level namespace, then the subparser writes its own default over
    it, and the flag silently does nothing.

    argparse.SUPPRESS as the default means the subparser writes nothing
    when the flag is absent, so whichever position it appears in wins.

        common = global_flags('--json')
        ap = argparse.ArgumentParser(parents=[common])
        sub.add_parser('status', parents=[common])
    """
    parser = argparse.ArgumentParser(add_help=False)
    for name in names:
        parser.add_argument(name, action='store_true',
                            default=argparse.SUPPRESS)
    for name, default in flags.items():
        parser.add_argument(f'--{name.replace("_", "-")}',
                            default=argparse.SUPPRESS)
    return parser


def parse_args(parser, default_cmd: str | None = None,
               argv: list[str] | None = None,
               defaults: dict | None = None):
    """
    Parse, defaulting to a subcommand without discarding the flags.

    Re-parsing `[default_cmd]` alone loses everything the user typed,
    so `tool --json` silently drops --json. Pass the original argv
    through instead.

    `defaults` fills in any flag suppressed by global_flags(), since a
    suppressed flag is simply absent from the namespace when unused.
    """
    if argv is None:
        argv = sys.argv[1:]

    args = parser.parse_args(argv)

    if getattr(args, 'cmd', None) is None and default_cmd:
        args = parser.parse_args([default_cmd] + argv)

    for key, value in (defaults or {}).items():
        if not hasattr(args, key):
            setattr(args, key, value)

    return args


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
