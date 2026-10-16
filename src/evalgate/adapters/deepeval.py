"""``deepeval:<Metric>`` custom metrics (extra ``[deepeval]``).

``kind: custom, params: {metric: "deepeval:ExactMatchMetric", actual_output: output.answer,
expected_output: expected.answer}``. Builds an ``LLMTestCase`` from selectors and returns
``metric.score``. DeepEval telemetry is turned off before import.
"""

from __future__ import annotations

import importlib
import os
from collections.abc import Callable
from typing import Any

from evalgate.adapters._common import as_list, text_field
from evalgate.contracts import Case, TargetResult
from evalgate.metrics.base import context
from evalgate.suite.selectors import resolve

_FIELDS = ("input", "actual_output", "expected_output", "retrieval_context")


def _metric_class(name: str) -> Any:
    os.environ.setdefault("DEEPEVAL_TELEMETRY_OPT_OUT", "YES")
    module = importlib.import_module("deepeval.metrics")
    if not hasattr(module, name):
        raise KeyError(f"deepeval has no metric {name!r} (install evalgate[deepeval])")
    return getattr(module, name)


def make_metric(name: str) -> Callable[[Case, TargetResult, dict[str, Any]], tuple[float, dict[str, Any]]]:
    cls = _metric_class(name)

    def score(case: Case, result: TargetResult, params: dict[str, Any]) -> tuple[float, dict[str, Any]]:
        from deepeval.test_case import LLMTestCase

        ctx = context(case, result)
        test_case = LLMTestCase(
            input=text_field(case, result, params, "input", "input.question") or "",
            actual_output=text_field(case, result, params, "actual_output", "output.answer") or "",
            expected_output=text_field(case, result, params, "expected_output", "expected.answer"),
            retrieval_context=as_list(resolve(params.get("retrieval_context"), ctx))
            if params.get("retrieval_context")
            else None,
        )
        metric = cls(**{k: v for k, v in params.items() if k not in _FIELDS})
        metric.measure(test_case)
        if metric.score is None:  # never default to 0.0: that is the best value of Hallucination, Toxicity, Bias
            raise ValueError(f"deepeval {name} returned no score")
        return float(metric.score), {
            "adapter": "deepeval",
            "deepeval_metric": name,
            "reason": str(getattr(metric, "reason", "") or "")[:200],
        }

    return score
