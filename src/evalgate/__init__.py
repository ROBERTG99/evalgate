"""evalgate: golden sets, deterministic metrics and calibrated LLM judges as a CI gate.

The top-level import stays light (no numpy, duckdb or provider SDKs) so that ``import evalgate`` is fast.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

__version__ = "0.1.0"

if TYPE_CHECKING:
    from evalgate.contracts import Case, MetricScore, StepRecord, TargetResult
    from evalgate.metrics.base import Metric
    from evalgate.metrics.registry import metric

__all__ = ["Case", "Metric", "MetricScore", "StepRecord", "TargetResult", "__version__", "metric"]


def __getattr__(name: str) -> Any:
    if name in ("Case", "MetricScore", "StepRecord", "TargetResult"):
        from evalgate import contracts

        return getattr(contracts, name)
    if name == "metric":
        from evalgate.metrics.registry import metric

        return metric
    if name == "Metric":
        from evalgate.metrics.base import Metric

        return Metric
    raise AttributeError(f"module 'evalgate' has no attribute {name!r}")
