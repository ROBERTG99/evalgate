"""Step pricing and latency percentiles (FR-6)."""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from functools import cache
from importlib import resources
from typing import Any

import yaml

from evalgate.contracts import StepRecord


@cache
def price_table() -> dict[str, dict[str, float]]:
    text = resources.files("evalgate").joinpath("pricing.yaml").read_text(encoding="utf-8")
    data: dict[str, Any] = yaml.safe_load(text)
    return {name: {"input": float(p["input"]), "output": float(p["output"])} for name, p in data["models"].items()}


def has_price(model: str | None) -> bool:
    return model is not None and model in price_table()


def step_cost(model: str | None, input_tokens: int, output_tokens: int) -> float:
    """Cost in USD: ``(input_tokens * input_price + output_tokens * output_price) / 1e6``.

    Unknown or missing models cost 0 and are reported by :func:`unpriced_models`.
    """
    if model is None or model not in price_table():
        return 0.0
    price = price_table()[model]
    return (input_tokens * price["input"] + output_tokens * price["output"]) / 1_000_000


def price_steps(steps: Iterable[StepRecord]) -> list[StepRecord]:
    """Fill ``cost_usd`` on steps that carry tokens but no cost."""
    priced = []
    for original in steps:
        step = original
        if step.cost_usd == 0 and (step.input_tokens or step.output_tokens):
            step = step.model_copy(update={"cost_usd": step_cost(step.model, step.input_tokens, step.output_tokens)})
        priced.append(step)
    return priced


def unpriced_models(steps: Iterable[StepRecord]) -> set[str]:
    return {s.model for s in steps if s.model and not has_price(s.model) and (s.input_tokens or s.output_tokens)}


def percentile(values: Sequence[float], q: float) -> float:
    """Linear-interpolated percentile (numpy's default method), without numpy."""
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    pos = (len(ordered) - 1) * q / 100.0
    lo, hi = math.floor(pos), math.ceil(pos)
    return float(ordered[lo] + (ordered[hi] - ordered[lo]) * (pos - lo))
