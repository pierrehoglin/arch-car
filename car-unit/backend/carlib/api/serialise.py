"""
Rebuilding dataclasses from JSON.

The server sends `to_dict()` output; the client has to turn it back
into the same dataclass so callers -- CLI display code especially --
work unchanged whether they got the object from the library or over
HTTP.

`dataclasses.asdict()` recurses into nested dataclasses and lists, so
the reverse has to as well: RadioState holds an Rds, SourceState holds
a list of Player.
"""

import typing
from dataclasses import fields, is_dataclass
from typing import Any, TypeVar

T = TypeVar('T')


def _unwrap_optional(annotation):
    """`int | None` -> int. Anything else is returned unchanged."""
    origin = typing.get_origin(annotation)
    if origin is typing.Union or str(origin) == 'types.UnionType':
        args = [a for a in typing.get_args(annotation)
                if a is not type(None)]
        if len(args) == 1:
            return args[0]
    return annotation


def from_dict(cls: type[T], data: Any) -> T:
    """
    Build a dataclass from a plain dict.

    Unknown keys are ignored rather than raising: a newer server may
    send fields this client does not know about, and refusing to parse
    the whole response over one extra key would make version skew
    fatal for no reason.

    Missing keys fall back to the dataclass default.
    """
    if not is_dataclass(cls):
        return data
    if not isinstance(data, dict):
        return cls()

    hints = typing.get_type_hints(cls)
    kwargs = {}

    for f in fields(cls):
        if f.name not in data:
            continue

        value = data[f.name]
        annotation = _unwrap_optional(hints.get(f.name, Any))
        origin = typing.get_origin(annotation)

        if is_dataclass(annotation) and isinstance(value, dict):
            kwargs[f.name] = from_dict(annotation, value)
        elif origin is list and isinstance(value, list):
            args = typing.get_args(annotation)
            inner = args[0] if args else None
            if inner is not None and is_dataclass(inner):
                kwargs[f.name] = [from_dict(inner, v) for v in value]
            else:
                kwargs[f.name] = value
        else:
            kwargs[f.name] = value

    return cls(**kwargs)
