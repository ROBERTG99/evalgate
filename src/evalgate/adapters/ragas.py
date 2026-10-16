"""``ragas:<Metric>`` custom metrics (extra ``[ragas]``).

``kind: custom, params: {metric: "ragas:ExactMatch", response: output.answer, reference: expected.answer}``.
The adapter builds a ragas ``SingleTurnSample`` from selectors (``user_input``, ``response``, ``reference``,
``retrieved_contexts``) and returns the ragas score. Metrics that need an LLM use ragas' own LLM settings;
evalgate's offline gates should use the non-LLM ones (ExactMatch, StringPresence, NonLLMStringSimilarity,
BleuScore, RougeScore).
"""

from __future__ import annotations

import importlib
import warnings
from collections.abc import Callable
from typing import Any

from evalgate.adapters._common import as_list, run_coroutine, text_field
from evalgate.contracts import Case, TargetResult
from evalgate.metrics.base import context
from evalgate.suite.selectors import resolve


def _metric_class(name: str) -> Any:
    for module_name in ("ragas.metrics",):  # the SingleTurnSample API (collections use another one)
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", DeprecationWarning)
                module = importlib.import_module(module_name)
                found = getattr(module, name, None)
        except ImportError:
            continue
        if found is not None:
            return found
    raise KeyError(f"ragas has no metric {name!r} (install evalgate[ragas])")


def make_metric(name: str) -> Callable[[Case, TargetResult, dict[str, Any]], tuple[float, dict[str, Any]]]:
    cls = _metric_class(name)

    def score(case: Case, result: TargetResult, params: dict[str, Any]) -> tuple[float, dict[str, Any]]:
        from ragas.dataset_schema import SingleTurnSample

        ctx = context(case, result)
        sample = SingleTurnSample(
            user_input=text_field(case, result, params, "user_input", "input.question"),
            response=text_field(case, result, params, "response", "output.answer"),
            reference=text_field(case, result, params, "reference", "expected.answer"),
            retrieved_contexts=as_list(resolve(params.get("retrieved_contexts"), ctx))
            if params.get("retrieved_contexts")
            else None,
        )
        options = {
            k: v for k, v in params.items() if k not in ("user_input", "response", "reference", "retrieved_contexts")
        }
        metric = cls(**options)
        value = float(run_coroutine(metric.single_turn_ascore(sample)))
        return value, {"adapter": "ragas", "ragas_metric": name}

    return score
