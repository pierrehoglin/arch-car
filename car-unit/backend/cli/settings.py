#!/usr/bin/env python3
"""
User settings.

    settings                        # every setting, defaults included
    settings show --set             # only what has been changed
    settings describe fm.gain       # what one setting is for
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


def _covered(key: str, stored: set[str]) -> bool:
    """
    Whether a declared key is already shown by what is stored.

    Exactly, or through its children: fm.last is stored as a dict and
    shown flattened -- fm.last.frequency, fm.last.gain -- so listing
    fm.last again as a default would show the same thing twice.
    """
    return key in stored or any(s.startswith(key + '.') for s in stored)


def rows_for(data: dict, only_set: bool) -> list[dict]:
    """
    One row per setting: what it is, and whether it was set.

    Everything declared in the catalogue, with its default where it
    has not been set -- so the list doubles as a reference to what can
    be configured -- plus anything stored that the catalogue does not
    know about, which still works and should still be visible.
    """
    stored = flatten(data)
    stored_keys = {key for key, _ in stored}
    rows = []

    for key, value in stored:
        entry = settings.known(key)
        rows.append({
            'key': key,
            'value': value,
            'set': True,
            'default': entry.default if entry else None,
            'kind': entry.kind if entry else '',
            'description': entry.description if entry else '',
        })

    if not only_set:
        for entry in settings.catalogue():
            if _covered(entry.key, stored_keys):
                continue
            rows.append({
                'key': entry.key,
                'value': entry.default,
                'set': False,
                'default': entry.default,
                'kind': entry.kind,
                'description': entry.description,
            })

    rows.sort(key=lambda row: row['key'])
    return rows


def shown(value) -> str:
    """A value for the table. Empty and missing are said out loud: a
    blank column reads as a bug in the listing."""
    if value is None:
        return 'null'
    if value == '':
        return '""'
    return render(value)


async def cmd_show(args) -> None:
    data = settings.reload()
    rows = rows_for(data, only_set=args.set)

    if args.json:
        emit_json(rows)
        return

    if not rows:
        print('nothing set -- settings shows every setting with its '
              'default', file=sys.stderr)
        print(f'{settings.path()}', file=sys.stderr)
        return

    width = max(len(row['key']) for row in rows)

    for row in rows:
        line = f"{row['key']:<{width}}  {shown(row['value'])}"
        if not row['set']:
            line += '  (default)'
        print(line)

    changed = sum(1 for row in rows if row['set'])
    summary = (f'{changed} set' if args.set else
               f'{changed} set, {len(rows) - changed} at their default')
    print(f'\n{summary}. settings describe <key> says what one is for.',
          file=sys.stderr)
    print(f'{settings.path()}', file=sys.stderr)


async def cmd_describe(args) -> None:
    """What a setting is for."""
    entry = settings.known(args.key)
    if entry is None:
        if args.json:
            emit_json(None)
            return
        print(f'{args.key} is not a known setting', file=sys.stderr)
        print('settings lists the ones that are',
              file=sys.stderr)
        return

    sentinel = object()
    current = settings.get(args.key, sentinel)

    if args.json:
        emit_json({
            'key': entry.key,
            'kind': entry.kind,
            'default': entry.default,
            'description': entry.description,
            'value': None if current is sentinel else current,
            'set': current is not sentinel,
        })
        return

    print(entry.key)
    print(f'  {entry.description}')
    print(f'  type:    {entry.kind}')
    print(f'  default: {render(entry.default)}')
    if current is not sentinel:
        print(f'  value:   {render(current)}')
    else:
        print('  value:   (not set)')


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

    p = sub.add_parser('show', parents=[common],
                       help='every setting, defaults included')
    p.set_defaults(fn=cmd_show)
    p.add_argument('--set', action='store_true',
                   help='only settings that have been changed')
    # Kept so scripts that pass it still work. Listing everything is
    # what show does now.
    p.add_argument('--all', action='store_true',
                   help=argparse.SUPPRESS)

    p = sub.add_parser('describe', parents=[common],
                       help='what a setting is for')
    p.set_defaults(fn=cmd_describe)
    p.add_argument('key')

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

    args = parse_args(ap, 'show',
                      defaults={'json': False, 'all': False,
                                'set': False})
    return run(args.fn(args))


if __name__ == '__main__':
    sys.exit(main())
