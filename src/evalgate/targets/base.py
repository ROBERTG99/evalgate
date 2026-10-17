"""Target interface and result coercion."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from evalgate.contracts import StepRecord, TargetResult

Target = Callable[[dict[str, Any]], Awaitable[TargetResult]]

_STEP_FIELDS = set(StepRecord.model_fields)
_KINDS = {"llm", "tool", "retrieval", "judge", "target", "other"}


class TargetError(Exception):
    """A target failed in a way that must not be retried (e.g. HTTP 400)."""


class RetriableTargetError(TargetError):
    """A target failed transiently (connection error, 408, 429, 5xx)."""


def coerce_steps(raw: Any) -> list[StepRecord]:
    """Turn step-like dicts (e.g. from an HTTP target) into StepRecords, keeping known fields."""
    steps: list[StepRecord] = []
    if not isinstance(raw, list):
        return steps
    for i, item in enumerate(raw):
        if isinstance(item, StepRecord):
            steps.append(item)
            continue
        if not isinstance(item, dict):
            continue
        data = {k: v for k, v in item.items() if k in _STEP_FIELDS}
        data.setdefault("step", i)
        if "node" not in data:
            data["node"] = str(item.get("name") or item.get("tool") or f"step-{i}")
        if data.get("kind") not in _KINDS:
            data["kind"] = "other"
        try:
            steps.append(StepRecord.model_validate(data))
        except ValueError:
            steps.append(StepRecord(step=i, node=str(data["node"]), kind="other"))
    return steps


def coerce_result(value: Any) -> TargetResult:
    """Accept a TargetResult, a dict (``steps`` key becomes step records) or a string."""
    if isinstance(value, TargetResult):
        return value
    if isinstance(value, str):
        return TargetResult(output=value)
    if isinstance(value, dict):
        return TargetResult(output=value, steps=coerce_steps(value.get("steps")))
    raise TargetError(f"target returned {type(value).__name__}; expected TargetResult, dict or str")
