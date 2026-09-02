"""Every settings key used in the code should be in the catalogue."""
import ast, pathlib, sys
from carlib.core import settings

GETTERS = {'get', 'set', 'has', 'delete', 'get_int', 'get_float',
           'get_bool', 'get_str', 'get_list', 'get_dict'}

used = {}


def scan(path, tree):
    # settings.get('a.b') / settings.set('a.b', ...)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        f = node.func
        if not isinstance(f, ast.Attribute) or f.attr not in GETTERS:
            continue
        if not node.args or not isinstance(node.args[0], ast.Constant):
            continue
        key = node.args[0].value
        if not isinstance(key, str):
            continue

        base = f.value
        prefix = ''
        if isinstance(base, ast.Name) and base.id == 'settings':
            prefix = ''
        elif isinstance(base, ast.Name) and base.id == '_settings':
            # section('fm') in fm.py
            prefix = 'fm.'
        else:
            continue
        used.setdefault(prefix + key, []).append(f'{path}:{node.lineno}')


for path in sorted(pathlib.Path('carlib').rglob('*.py')):
    scan(path, ast.parse(path.read_text()))
for path in sorted(pathlib.Path('cli').rglob('*.py')):
    scan(path, ast.parse(path.read_text()))

declared = settings.declared_keys()
missing = {k: v for k, v in used.items() if k not in declared}
unused = declared - set(used)

print(f'  keys used in code:  {len(used)}')
print(f'  keys in catalogue:  {len(declared)}')

if missing:
    print('\n  NOT IN CATALOGUE:')
    for k, where in sorted(missing.items()):
        print(f'    {k:<24} {where[0]}')
if unused:
    print('\n  in catalogue, never read (set by CLI, or documentation):')
    for k in sorted(unused):
        print(f'    {k}')

sys.exit(1 if missing else 0)
