"""
D-Bus variant handling.

sdbus hands back variants as (signature, value) tuples. Almost every
property read needs unwrapping, so it lives here rather than being
copy-pasted per module.
"""

from typing import Any


def unwrap(variant: Any) -> Any:
    """
    Turn a (signature, value) tuple into its value.

    Passes anything else through unchanged, so it is safe to call on
    values that may or may not be wrapped.
    """
    if isinstance(variant, tuple) and len(variant) == 2 \
            and isinstance(variant[0], str):
        return variant[1]
    return variant


def props(raw: dict | None) -> dict:
    """Unwrap every value in a property dict."""
    return {k: unwrap(v) for k, v in (raw or {}).items()}


def as_variant(value: Any) -> tuple[str, Any]:
    """
    Wrap a Python value for sending as a variant.

    Only covers the types these interfaces actually take. Pass an
    explicit tuple when you need a specific numeric width -- notably
    'y' (byte) for oFono volume levels, which this would otherwise
    guess as 'i'.
    """
    if isinstance(value, bool):
        return ('b', value)
    if isinstance(value, int):
        return ('i', value)
    if isinstance(value, str):
        return ('s', value)
    if isinstance(value, (list, tuple)):
        return ('as', list(value))
    raise TypeError(f'no variant mapping for {type(value).__name__}')
