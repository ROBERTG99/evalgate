"""``python: "module:callable"`` targets. Sync callables run in a worker thread."""

from __future__ import annotations

import asyncio
import importlib
import inspect
from typing import Any

from evalgate.contracts import TargetResult
from evalgate.errors import InvalidInputError
from evalgate.targets.base import Target, coerce_result


def import_object(ref: str) -> Any:
    module_name, _, attr = ref.partition(":")
    try:
        module = importlib.import_module(module_name)
    except ImportError as exc:
        raise InvalidInputError(ref, "", f"cannot import module {module_name!r}: {exc}") from exc
    try:
        return getattr(module, attr)
    except AttributeError as exc:
        raise InvalidInputError(ref, "", f"module {module_name!r} has no attribute {attr!r}") from exc


def python_target(ref: str) -> Target:
    fn = import_object(ref)
    if not callable(fn):
        raise InvalidInputError(ref, "", "target is not callable")
    is_async = inspect.iscoroutinefunction(fn)

    async def call(case_input: dict[str, Any]) -> TargetResult:
        if is_async:
            value = await fn(case_input)
        else:
            value = await asyncio.to_thread(fn, case_input)
        return coerce_result(value)

    return call
