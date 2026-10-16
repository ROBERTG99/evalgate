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


def clamp(value: float) -> float:
    if math.isnan(value):
        return 0.0
    return max(0.0, min(1.0, float(value)))


class BaseMetric:
    """Common plumbing: ``name``, ``spec`` and the per-case pass level ``pass_at``."""

    default_pass_at = 1.0

    def __init__(self, spec: MetricSpec) -> None:
        self.spec = spec
        self.name = spec.name
        self.params: dict[str, Any] = dict(spec.params)
        self.pass_at = float(self.params.get("pass_at", self.default_pass_at))

    def make(self, value: float, **details: Any) -> MetricScore:
        v = clamp(value)
        passed = v >= self.pass_at if self.spec.direction == "higher" else v <= self.pass_at
        return MetricScore(name=self.name, value=v, passed=passed, details=details)

    def score(self, case: Case, result: TargetResult) -> MetricScore:  # pragma: no cover - abstract
        raise NotImplementedError
