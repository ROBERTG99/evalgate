"""Dotted-path selectors rooted at ``input``, ``output``, ``expected`` or ``meta``."""

from __future__ import annotations

from typing import Any

ROOTS = ("input", "output", "expected", "meta")
_MISSING = object()


class SelectorError(ValueError):
    pass


def validate_selector(path: str) -> None:
    root = path.split(".", 1)[0]
    if root not in ROOTS:
        raise SelectorError(f"selector {path!r} must start with one of {', '.join(ROOTS)}")


def select(path: str, context: dict[str, Any], default: Any = None) -> Any:
    """Resolve ``output.items.0.name`` against ``{"input": ..., "output": ..., ...}``."""
    validate_selector(path)
    current: Any = context
    for part in path.split("."):
        if isinstance(current, dict):
            current = current.get(part, _MISSING)
        elif isinstance(current, list) and part.lstrip("-").isdigit():
            idx = int(part)
            current = current[idx] if -len(current) <= idx < len(current) else _MISSING
        else:
            current = _MISSING
        if current is _MISSING:
            return default
    return current


def is_selector(value: Any) -> bool:
    return isinstance(value, str) and value.split(".", 1)[0] in ROOTS


def resolve(value: Any, context: dict[str, Any]) -> Any:
    """Selectors are resolved; any other value is a literal."""
    return select(value, context) if is_selector(value) else value
