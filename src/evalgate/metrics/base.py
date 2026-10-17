"""Metric protocol and helpers."""

from __future__ import annotations

import math
from typing import Any, Protocol, runtime_checkable

from evalgate.contracts import Case, MetricScore, MetricSpec, TargetResult


@runtime_checkable
class Metric(Protocol):
    name: str

    def score(self, case: Case, result: TargetResult) -> MetricScore: ...


def context(case: Case, result: TargetResult | None) -> dict[str, Any]:
    """The selector context of one case."""
    return {
        "input": case.input,
        "output": result.output if result is not None else None,
        "expected": case.expected or {},
        "meta": case.meta,
    }


def worst_score(direction: str) -> float:
    """The score of a case that produced no output: scores live in [0, 1], so the worst end of the metric."""
    return 1.0 if direction == "lower" else 0.0


def best_score(direction: str) -> float:
    """The score of a case a metric skips on purpose (``skip_missing``): it neither helps nor hurts the gate's
    threshold more than a perfect case would, whatever the direction."""
    return 1.0 - worst_score(direction)


def clamp(value: float) -> float:
    """Clip a score to [0, 1]. A non-finite value is a broken metric, never a score: the runner records the
    error as a metric error and the gate fails closed (clipping NaN to 0 would be the best value of a
    lower-is-better metric)."""
    if not math.isfinite(value):
        raise ValueError(f"metric value {value!r} is not a finite number")
    return max(0.0, min(1.0, float(value)))


class BaseMetric:
    """Common plumbing: ``name``, ``spec`` and the per-case pass level ``pass_at``."""

    default_pass_at = 1.0

    def __init__(self, spec: MetricSpec) -> None:
        self.spec = spec
        self.name = spec.name
        self.params: dict[str, Any] = dict(spec.params)
        # The per-case pass level mirrors for lower-is-better metrics (a default of 1.0 becomes 0.0).
        mirrored = 1.0 - self.default_pass_at if spec.direction == "lower" else self.default_pass_at
        self.pass_at = float(self.params.get("pass_at", mirrored))

    def make(self, value: float, **details: Any) -> MetricScore:
        if "problem" in details:  # the case could not be measured: the worst value for the metric's direction
            value = worst_score(self.spec.direction)
        v = clamp(value)
        passed = v >= self.pass_at if self.spec.direction == "higher" else v <= self.pass_at
        return MetricScore(name=self.name, value=v, passed=passed, details=details)

    def score(self, case: Case, result: TargetResult) -> MetricScore:  # pragma: no cover - abstract
        raise NotImplementedError
