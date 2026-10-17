"""Budgets: live cost estimates before a run and hard stops during it (FR-6, NFR-4)."""

from __future__ import annotations

import threading
from dataclasses import dataclass

from evalgate import config
from evalgate.accounting import step_cost
from evalgate.errors import BudgetAbortError

# Conservative per-call token estimates for one judge call (prompt, rubric, candidate; verdict JSON).
EST_JUDGE_INPUT_TOKENS = 1_200
EST_JUDGE_OUTPUT_TOKENS = 300


@dataclass(frozen=True)
class Estimate:
    calls: int
    cost_usd: float
    budget_usd: float

    @property
    def over(self) -> bool:
        return self.cost_usd > self.budget_usd

    def describe(self) -> str:
        return (
            f"live estimate: {self.calls} judge calls, about USD {self.cost_usd:.4f} "
            f"(budget LIVE_EVAL_BUDGET_USD={self.budget_usd:.2f})"
        )


def estimate_judge_cost(
    n_cases: int, judge_metrics: list[tuple[str, int]], budget_usd: float | None = None
) -> Estimate:
    """Estimate the cost of judge calls. ``judge_metrics`` holds ``(model, calls_per_case)`` pairs."""
    calls = 0
    cost = 0.0
    for model, per_case in judge_metrics:
        n = n_cases * per_case
        calls += n
        cost += n * step_cost(model, EST_JUDGE_INPUT_TOKENS, EST_JUDGE_OUTPUT_TOKENS)
    return Estimate(
        calls=calls, cost_usd=cost, budget_usd=config.live_budget_usd() if budget_usd is None else budget_usd
    )


def enforce_estimate(estimate: Estimate) -> None:
    if estimate.over:
        raise BudgetAbortError(f"{estimate.describe()}: over budget, no provider call was made")


class SpendGuard:
    """Thread-safe running total; raises once live spend would pass the budget."""

    def __init__(self, budget_usd: float | None) -> None:
        self.budget_usd = budget_usd
        self.spent_usd = 0.0
        self._lock = threading.Lock()

    def check(self) -> None:
        if self.budget_usd is not None and self.spent_usd >= self.budget_usd:
            raise BudgetAbortError(
                f"live spend USD {self.spent_usd:.4f} reached LIVE_EVAL_BUDGET_USD={self.budget_usd:.2f}"
            )

    def add(self, cost_usd: float) -> None:
        with self._lock:
            self.spent_usd += cost_usd
