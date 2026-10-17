"""Retries with exponential backoff and full jitter for target calls."""

from __future__ import annotations

import asyncio
import random
from collections.abc import Awaitable, Callable
from typing import Any

from evalgate.targets.base import RetriableTargetError

BASE_DELAY_S = 0.5
MAX_DELAY_S = 8.0


class CaseFailure(Exception):
    def __init__(self, error: str, attempts: int) -> None:
        super().__init__(error)
        self.error = error
        self.attempts = attempts


def backoff_delay(attempt: int, rng: random.Random, base: float = BASE_DELAY_S, cap: float = MAX_DELAY_S) -> float:
    """Full jitter: uniform(0, min(cap, base * 2**attempt))."""
    return rng.uniform(0, min(cap, base * (2**attempt)))


async def call_with_retries[T](
    fn: Callable[[Any], Awaitable[T]],
    arg: Any,
    *,
    retries: int,
    timeout_s: float,
    rng: random.Random | None = None,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> tuple[T, int]:
    """Call ``fn(arg)``; retry timeouts and :class:`RetriableTargetError` up to ``retries`` times."""
    rng = rng or random.Random()  # noqa: S311 - jitter, not security
    attempts = 0
    while True:
        attempts += 1
        try:
            return await asyncio.wait_for(fn(arg), timeout=timeout_s), attempts
        except TimeoutError:
            error = "timeout"
        except RetriableTargetError as exc:
            error = str(exc) or "retriable error"
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            raise CaseFailure(f"{exc.__class__.__name__}: {exc}"[:500], attempts) from exc
        if attempts > retries:
            raise CaseFailure(error, attempts)
        await sleep(backoff_delay(attempts - 1, rng))
