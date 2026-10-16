"""Deterministic metrics (FR-3): exact, json_schema, numeric_tolerance, contains_all, regex, tool_calls."""

from __future__ import annotations

import json
import re
from functools import cached_property
from pathlib import Path
from typing import Any

from evalgate.contracts import Case, MetricScore, MetricSpec, TargetResult
from evalgate.metrics.base import BaseMetric, best_score, context, worst_score
from evalgate.suite.selectors import resolve


def _norm(value: Any) -> Any:
    if isinstance(value, str):
        return " ".join(value.split()).casefold()
    return value


class ExactMetric(BaseMetric):
    """1.0 when ``actual == expected`` (optionally whitespace and case normalised)."""

    def score(self, case: Case, result: TargetResult) -> MetricScore:
        ctx = context(case, result)
        actual = resolve(self.params.get("actual", "output"), ctx)
        expected = resolve(self.params.get("expected", "expected"), ctx)
        if expected is None and self.params.get("skip_missing", False):
            return self.make(best_score(self.spec.direction), skipped="no expected value for this case")
        if self.params.get("normalize", False):
            actual, expected = _norm(actual), _norm(expected)
        return self.make(1.0 if actual == expected else 0.0, actual=_excerpt(actual), expected=_excerpt(expected))


class JsonSchemaMetric(BaseMetric):
    """1.0 when the selected value validates against a JSON Schema (inline ``schema`` or ``schema_path``)."""

    def __init__(self, spec: MetricSpec) -> None:
        super().__init__(spec)
        _ = self.validator  # compile before the run: lazy compilation would stall the event loop mid-run

    @cached_property
    def validator(self) -> Any:
        from jsonschema import Draft202012Validator

        schema = self.params.get("schema")
        if schema is None:
            schema = json.loads(Path(str(self.params["schema_path"])).read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        return Draft202012Validator(schema)

    def score(self, case: Case, result: TargetResult) -> MetricScore:
        actual = resolve(self.params.get("actual", "output"), context(case, result))
        errors = sorted(self.validator.iter_errors(actual), key=lambda e: list(e.path))
        if errors:
            first = errors[0]
            where = "/".join(str(p) for p in first.path) or "<root>"
            return self.make(0.0, problem=f"{where}: {first.message}"[:300], n_errors=len(errors))
        return self.make(1.0)


_NUM = re.compile(r"[-+]?\d[\d,]*(?:\.\d+)?|[-+]?\.\d+")


def to_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        match = _NUM.search(value)
        if match:
            try:
                return float(match.group(0).replace(",", ""))
            except ValueError:
                return None
    return None


class NumericToleranceMetric(BaseMetric):
    """1.0 when ``|actual - expected| <= max(abs_tol, rel_tol * |expected|)``."""

    def score(self, case: Case, result: TargetResult) -> MetricScore:
        ctx = context(case, result)
        actual = to_number(resolve(self.params.get("actual", "output"), ctx))
        expected = to_number(resolve(self.params.get("expected", "expected"), ctx))
        if actual is None or expected is None:
            return self.make(0.0, problem="not a number", actual=actual, expected=expected)
        tol = max(float(self.params.get("abs_tol", 0.0)), float(self.params.get("rel_tol", 0.0)) * abs(expected))
        diff = abs(actual - expected)
        return self.make(1.0 if diff <= tol + 1e-12 else 0.0, actual=actual, expected=expected, diff=diff)


class ContainsAllMetric(BaseMetric):
    """1.0 when the text contains every expected phrase (case-insensitive by default)."""

    def score(self, case: Case, result: TargetResult) -> MetricScore:
        ctx = context(case, result)
        actual = resolve(self.params.get("actual", "output"), ctx)
        values = resolve(self.params.get("expected", self.params.get("values", [])), ctx)
        if isinstance(values, str):
            values = [values]
        text = actual if isinstance(actual, str) else json.dumps(actual, sort_keys=True) if actual else ""
        insensitive = bool(self.params.get("case_insensitive", True))
        hay = text.casefold() if insensitive else text
        missing = [v for v in values or [] if (str(v).casefold() if insensitive else str(v)) not in hay]
        return self.make(0.0 if missing else 1.0, missing=missing[:10])


class RegexMetric(BaseMetric):
    """1.0 when ``pattern`` matches the selected string (``re.search``). ``pattern`` may be a selector."""

    def __init__(self, spec: MetricSpec) -> None:
        super().__init__(spec)
        self._compiled: dict[str, re.Pattern[str]] = {}

    def compiled(self, pattern: str) -> re.Pattern[str]:
        if pattern not in self._compiled:
            flags = re.IGNORECASE if "i" in str(self.params.get("flags", "")) else 0
            self._compiled[pattern] = re.compile(pattern, flags)
        return self._compiled[pattern]

    def score(self, case: Case, result: TargetResult) -> MetricScore:
        ctx = context(case, result)
        pattern = resolve(self.params["pattern"], ctx)
        if pattern is None:
            if self.params.get("skip_missing", False):
                return self.make(best_score(self.spec.direction), skipped="no pattern for this case")
            return self.make(worst_score(self.spec.direction), problem="no pattern for this case")
        actual = resolve(self.params.get("actual", "output"), ctx)
        if actual is None:  # nothing to search is not a clean "no match" (a forbidden-pattern metric would pass)
            return self.make(0.0, problem="no value selected")
        text = actual if isinstance(actual, str) else json.dumps(actual, ensure_ascii=False, sort_keys=True)
        ok = self.compiled(str(pattern)).search(text) is not None
        return self.make(1.0 if ok else 0.0, actual=_excerpt(actual))


def _call_name(call: dict[str, Any]) -> str | None:
    for key in ("name", "tool", "node"):
        if isinstance(call.get(key), str):
            return str(call[key])
    return None


def _call_args(call: dict[str, Any]) -> dict[str, Any]:
    for key in ("args", "arguments", "input"):
        if isinstance(call.get(key), dict):
            return dict(call[key])
    return {}


def _subset(expected: dict[str, Any], actual: dict[str, Any]) -> bool:
    return all(k in actual and actual[k] == v for k, v in expected.items())


class ToolCallsMetric(BaseMetric):
    """1.0 when the expected tools appear in order (as a subsequence) with matching ``args_subset``."""

    def score(self, case: Case, result: TargetResult) -> MetricScore:
        ctx = context(case, result)
        actual_raw = resolve(self.params.get("actual", "output.steps"), ctx) or []
        expected = resolve(self.params.get("expected", "expected.tools"), ctx) or []
        calls = [c for c in actual_raw if isinstance(c, dict) and c.get("kind", "tool") == "tool" and _call_name(c)]
        names = [_call_name(c) for c in calls]
        if self.params.get("exact_sequence", False) and names != [e.get("name") for e in expected]:
            return self.make(0.0, reason="sequence differs", called=names)
        pos = 0
        for exp in expected:
            want, subset = exp.get("name"), exp.get("args_subset", {}) or {}
            while pos < len(calls) and not (_call_name(calls[pos]) == want and _subset(subset, _call_args(calls[pos]))):
                pos += 1
            if pos == len(calls):
                return self.make(0.0, missing=want, called=names)
            pos += 1
        return self.make(1.0, called=names)


def _excerpt(value: Any, limit: int = 200) -> Any:
    if isinstance(value, str) and len(value) > limit:
        return value[:limit] + "…"
    return value


BUILTIN: dict[str, type[BaseMetric]] = {
    "exact": ExactMetric,
    "json_schema": JsonSchemaMetric,
    "numeric_tolerance": NumericToleranceMetric,
    "contains_all": ContainsAllMetric,
    "regex": RegexMetric,
    "tool_calls": ToolCallsMetric,
}
