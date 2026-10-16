import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from evalgate.stats.bootstrap import mean_ci, paired_delta_ci
from evalgate.stats.gate import check, compare_metric, is_regression
from tests.factories import make_report

BASE = [1.0] * 120 + [0.0] * 30


def test_seeded_identical() -> None:
    cand = BASE[:]
    for i in range(10):
        cand[i] = 0.0
    a = paired_delta_ci(BASE, cand, seed=1337)
    b = paired_delta_ci(BASE, cand, seed=1337)
    c = paired_delta_ci(BASE, cand, seed=7)
    assert a == b
    assert (a.low, a.high) != (c.low, c.high)
    assert a.resamples == 10_000 and a.n == 150


def test_regression_6_7pp_fails_0_7pp_passes() -> None:
    drop10 = BASE[:]
    for i in range(10):
        drop10[i] = 0.0
    drop1 = BASE[:]
    drop1[0] = 0.0
    base = make_report({"acc": BASE}, threshold=0.5)
    big = make_report({"acc": drop10}, threshold=0.5)
    small = make_report({"acc": drop1}, threshold=0.5)
    r_big = check(big, report_sha256="x", baseline=base, max_regression_pp=1.0)
    assert not r_big.passed
    f = r_big.failures[0]
    assert f.reason == "regression"
    assert f.delta_pp == pytest.approx(-6.6667, abs=1e-3)
    assert f.ci_high_pp < 0
    r_small = check(small, report_sha256="x", baseline=base, max_regression_pp=1.0)
    assert r_small.passed
    assert r_small.comparisons[0].delta_pp == pytest.approx(-0.6667, abs=1e-3)


def test_lower_direction_signs() -> None:
    base = make_report({"err": [0.0] * 150}, direction="lower")
    worse_vals = [1.0] * 10 + [0.0] * 140
    worse = make_report({"err": worse_vals}, direction="lower")
    better = make_report({"err": [0.0] * 150}, direction="lower")
    r = check(worse, report_sha256="x", baseline=base)
    assert not r.passed
    assert r.failures[0].reason == "regression"
    assert r.failures[0].delta_pp > 0 and r.failures[0].ci_low_pp > 0
    assert check(better, report_sha256="x", baseline=base).passed
    comp = compare_metric("err", base, worse, seed=1, resamples=1000)
    assert comp is not None
    assert is_regression(comp, "lower", 1.0)
    assert not is_regression(comp, "higher", 1.0)


def test_unpaired_cases_ignored_and_n_reported() -> None:
    base = make_report({"acc": [1.0, 1.0, 1.0]}, ids=["a", "b", "c"])
    cand = make_report({"acc": [1.0, 0.0, 0.0]}, ids=["a", "b", "z"])
    comp = compare_metric("acc", base, cand, seed=1, resamples=500)
    assert comp is not None
    assert comp.n_paired == 2


def test_threshold_budget_and_health_failures() -> None:
    rep = make_report(
        {"acc": [0.0, 1.0]},
        threshold=0.9,
        p95=640.0,
        cost=2.0,
        extensions={
            "budget": {"max_cost_usd": 1.0, "max_p95_ms": 500},
            "run_health": "degraded",
            "error_rate": 0.6,
            "metric_errors": {"acc": 1},
        },
    )
    reasons = sorted(f.reason for f in check(rep, report_sha256="x").failures)
    assert reasons == ["budget_cost", "budget_p95", "error", "error", "threshold"]


def test_ungated_metrics_do_not_fail() -> None:
    rep = make_report({"acc": [0.0]}, threshold=0.9, extensions={"gates": {"acc": False}})
    assert check(rep, report_sha256="x").passed


@settings(max_examples=25, deadline=None)
@given(st.lists(st.sampled_from([0.0, 0.5, 1.0]), min_size=2, max_size=60), st.integers(0, 2**32 - 1))
def test_identical_runs_delta_zero_ci_contains_zero(values: list[float], seed: int) -> None:
    ci = paired_delta_ci(values, values, seed=seed, resamples=500)
    assert ci.estimate == 0.0
    assert ci.low <= 0.0 <= ci.high


def test_mean_ci_bounds() -> None:
    ci = mean_ci([0.0, 1.0] * 50, seed=1)
    assert ci.low < 0.5 < ci.high
    assert mean_ci([], seed=1).n == 0
