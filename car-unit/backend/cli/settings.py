#!/usr/bin/env python3
"""
User settings.

    settings                        # show everything
    settings get fm.gain
    settings get fm.gain 40         # with a fallback
    settings set fm.gain 42
    settings set display.night true
    settings unset fm.gain
    settings path
    settings edit

Values are parsed as JSON where possible, so `42` is a number, `true`
is a boolean and `"42"` is a string. Anything that is not valid JSON is
stored as a string, which means quoting is usually unnecessary.

Stored in ~/.config/carlib/settings.json, written atomically so a
power cut cannot leave it half-written.
"""

import os
import sys
import json
import shutil
import argparse
import subprocess

from carlib.core import settings
from carlib.core.output import run, emit_json, global_flags, parse_args


def parse_value(text: str):
    """
    JSON where it parses, string otherwise.

    So `settings set fm.gain 42` stores a number, `settings set
    fm.name P3` stores a string, and neither needs quoting.
    """
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def flatten(data, prefix=''):
    """Nested dict to dotted key/value pairs, for display."""
    rows = []
    for key in sorted(data):
        value = data[key]
        path = f'{prefix}.{key}' if prefix else key
        if isinstance(value, dict) and value:
            rows.extend(flatten(value, path))
        else:
            rows.append((path, value))
    return rows


def render(value) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


async def cmd_show(args) -> None:
    data = settings.reload()

    if args.json:
        emit_json(data)
        return

    rows = flatten(data)
    if not rows:
        print('no settings')
        print(f'file: {settings.path()}', file=sys.stderr)
        return

    width = max(len(key) for key, _ in rows)
    for key, value in rows:
        print(f'{key:<{width}}  {render(value)}')

    print(f'\n{settings.path()}', file=sys.stderr)


async def cmd_get(args) -> None:
    sentinel = object()
    value = settings.get(args.key, sentinel)

    if value is sentinel:
        if args.default is not None:
            print(args.default)
            return
        raise KeyError(f'no such setting: {args.key}')

    if args.json:
        emit_json(value)
    else:
        print(render(value))


async def cmd_set(args) -> None:
    value = parse_value(args.value)
    settings.set(args.key, value)
    print(f'{args.key} = {render(value)}')


async def cmd_unset(args) -> None:
    if settings.delete(args.key):
        print(f'removed {args.key}')
    else:
        print(f'no such setting: {args.key}', file=sys.stderr)


async def cmd_path(args) -> None:
    print(settings.path())


async def cmd_edit(args) -> None:
    """
    Open the file in $EDITOR.

    Edits go through a temporary copy and are validated before being
    written back, so a typo cannot leave the unit with an unreadable
    settings file.
    """
    editor = os.environ.get('EDITOR') or os.environ.get('VISUAL')
    if not editor:
        for candidate in ('nvim', 'vim', 'nano', 'vi'):
            if shutil.which(candidate):
                editor = candidate
                break
    if not editor:
        print('no editor found; set $EDITOR', file=sys.stderr)
        print(f'file: {settings.path()}')
        return

    settings.path().parent.mkdir(parents=True, exist_ok=True)
    if not settings.path().exists():
        settings.save(settings.load())

    scratch = settings.path().with_suffix('.json.edit')
    shutil.copy2(settings.path(), scratch)

    try:
        subprocess.run([editor, str(scratch)], check=False)

        text = scratch.read_text(encoding='utf-8')
        try:
            data = json.loads(text) if text.strip() else {}
        except json.JSONDecodeError as exc:
            print(f'not valid JSON: {exc}', file=sys.stderr)
            print(f'changes left in {scratch}', file=sys.stderr)
            return

        if not isinstance(data, dict):
            print('top level must be an object', file=sys.stderr)
            return

        settings.save(data)
        print('saved')
    finally:
        try:
            scratch.unlink()
        except OSError:
            pass


def main() -> int:
    common = global_flags('--json')

    ap = argparse.ArgumentParser(
        description=__doc__.strip(),
        parents=[common],
        formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd')

    p = sub.add_parser('show', parents=[common], help='show everything')
    p.set_defaults(fn=cmd_show)

    p = sub.add_parser('get', parents=[common], help='read one setting')
    p.set_defaults(fn=cmd_get)
    p.add_argument('key', help='dotted path, e.g. fm.gain')
    p.add_argument('default', nargs='?', default=None,
                   help='printed when the key is missing')

    p = sub.add_parser('set', parents=[common], help='write one setting')
    p.set_defaults(fn=cmd_set)
    p.add_argument('key')
    p.add_argument('value')

    p = sub.add_parser('unset', parents=[common], help='remove a setting')
    p.set_defaults(fn=cmd_unset)
    p.add_argument('key')

    p = sub.add_parser('path', parents=[common],
                       help='where the file lives')
    p.set_defaults(fn=cmd_path)

    p = sub.add_parser('edit', parents=[common],
                       help='open in $EDITOR, validated on save')
    p.set_defaults(fn=cmd_edit)

    args = parse_args(ap, 'show', defaults={'json': False})
    return run(args.fn(args))


if __name__ == '__main__':
    sys.exit(main())
