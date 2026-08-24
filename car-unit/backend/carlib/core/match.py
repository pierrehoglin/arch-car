"""
Selecting one thing from a list by a loose identifier.

`bt_call.py` and `bt_media.py` each grew their own near-identical
matcher. This is that logic once: match on MAC in either notation, on an
object path fragment, or on a substring of a human-readable name.
"""

from typing import Callable, Sequence, TypeVar

from carlib.core.errors import NotFoundError, AmbiguousMatchError

T = TypeVar('T')


def normalise(text: str) -> str:
    """MACs appear as 20:F0:94:.. in the wild and 20_F0_94_.. in paths."""
    return (text or '').upper().replace(':', '_')


def select(items: Sequence[T],
           match: str,
           *,
           what: str,
           keys: Callable[[T], Sequence[str]],
           label: Callable[[T], str]) -> T:
    """
    Find the single item whose keys contain `match`.

    keys()  -> strings to search (path, MAC, name)
    label() -> what to call it in an error message

    Raises NotFoundError or AmbiguousMatchError rather than guessing:
    dialling from the wrong phone is worse than an error.
    """
    if not items:
        raise NotFoundError(what, match, [])

    needle = normalise(match)
    hits = []

    for item in items:
        for key in keys(item):
            if not key:
                continue
            if needle in normalise(key) or match.upper() in key.upper():
                hits.append(item)
                break

    if not hits:
        raise NotFoundError(what, match, [label(i) for i in items])
    if len(hits) > 1:
        raise AmbiguousMatchError(what, match, [label(i) for i in hits])

    return hits[0]


def select_optional(items: Sequence[T],
                    match: str | None,
                    *,
                    what: str,
                    keys: Callable[[T], Sequence[str]],
                    label: Callable[[T], str]) -> T:
    """
    As `select`, but with no identifier fall back to the only item.

    Refuses to choose when several are present. Useful for an API where
    the caller may reasonably omit the identifier on a single-phone
    system.
    """
    if match is not None:
        return select(items, match, what=what, keys=keys, label=label)

    if not items:
        raise NotFoundError(what, '<any>', [])
    if len(items) > 1:
        raise AmbiguousMatchError(
            what, '<any>', [label(i) for i in items])

    return items[0]
