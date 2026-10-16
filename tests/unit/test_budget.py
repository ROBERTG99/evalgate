import pytest

from evalgate.budget import SpendGuard, enforce_estimate, estimate_judge_cost
from evalgate.errors import BudgetAbortError


def test_live_estimate_exit_3() -> None:
    est = estimate_judge_cost(200, [("claude-opus-5-5", 2)], budget_usd=0.5)
    assert est.calls == 400
    assert est.cost_usd > 0.5
    with pytest.raises(BudgetAbortError) as info:
        enforce_estimate(est)
    assert info.value.exit_code == 3
    assert "no provider call was made" in str(info.value)


def test_estimate_under_budget_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LIVE_EVAL_BUDGET_USD", "2")
    est = estimate_judge_cost(60, [("claude-haiku-5-5", 2)])
    assert est.budget_usd == 2.0
    assert not est.over
    enforce_estimate(est)
    assert "LIVE_EVAL_BUDGET_USD=2.00" in est.describe()


def test_spend_guard_hard_stop() -> None:
    guard = SpendGuard(0.01)
    guard.add(0.006)
    guard.check()
    guard.add(0.006)
    with pytest.raises(BudgetAbortError):
        guard.check()
    unlimited = SpendGuard(None)
    unlimited.add(100)
    unlimited.check()
