"""Shared plumbing for third-party metric adapters."""

from __future__ import annotations

import asyncio
import concurrent.futures
from collections.abc import Coroutine
from typing import Any

from evalgate.contracts import Case, TargetResult
from evalgate.metrics.base import context
from evalgate.suite.selectors import resolve

_POOL = concurrent.futures.ThreadPoolExecutor(max_workers=4, thread_name_prefix="evalgate-adapter")


def run_coroutine(coro: Coroutine[Any, Any, Any]) -> Any:
    """Run a coroutine to completion from sync code, even inside a running event loop."""
    return _POOL.submit(asyncio.run, coro).result()


def text_field(case: Case, result: TargetResult, params: dict[str, Any], key: str, default: str) -> str | None:
    value = resolve(params.get(key, default), context(case, result))
    if value is None:
        return None
    return value if isinstance(value, str) else str(value)


def as_list(value: Any) -> list[str] | None:
    if value is None:
        return None
    if isinstance(value, list):
        return [str(v) for v in value]
    return [str(value)]
