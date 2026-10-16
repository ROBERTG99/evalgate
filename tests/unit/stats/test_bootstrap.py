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


def test_minimum_paired_cases_fail_closed() -> None:
    base = make_report({"acc": [1.0] * 9}, threshold=0.5)
    cand = make_report({"acc": [0.0] + [1.0] * 8}, threshold=0.5)
    result = check(cand, report_sha256="x", baseline=base)
    assert [f.reason for f in result.failures] == ["error"]
    assert result.failures[0].value == 9.0 and result.failures[0].threshold == 10.0
    one = check(make_report({"acc": [0.0]}), report_sha256="x", baseline=make_report({"acc": [1.0]}))
    assert [f.reason for f in one.failures] == ["error"]  # one case is never a supported regression
    none = check(
        make_report({"acc": [1.0] * 12}, ids=[f"a{i}" for i in range(12)]),
        report_sha256="x",
        baseline=make_report({"acc": [1.0] * 12}, ids=[f"b{i}" for i in range(12)]),
    )
    assert [f.reason for f in none.failures] == ["error"]


def test_gated_metric_missing_from_baseline_fails_closed() -> None:
    base = make_report({"acc": [1.0] * 20})
    cand = make_report({"acc": [1.0] * 20, "new": [1.0] * 20})
    result = check(cand, report_sha256="x", baseline=base)
    assert [(f.metric, f.reason) for f in result.failures] == [("new", "error")]


def test_boundaries_exactly_minus_one_pp_and_ci_touching_zero() -> None:
    from evalgate.contracts import Comparison

    at_limit = Comparison(
        metric="m", baseline=1, candidate=0.99, delta_pp=-1.0, ci_low_pp=-3.0, ci_high_pp=-0.1, n_paired=100
    )
    assert not is_regression(at_limit, "higher", 1.0)  # must be worse than -1.0 pp
    touching = at_limit.model_copy(update={"delta_pp": -5.0, "ci_high_pp": 0.0})
    assert not is_regression(touching, "higher", 1.0)  # the CI must exclude 0
    assert is_regression(touching.model_copy(update={"ci_high_pp": -0.01}), "higher", 1.0)


@settings(max_examples=20, deadline=None)
@given(
    st.lists(st.tuples(st.sampled_from([0.0, 1.0]), st.sampled_from([0.0, 1.0])), min_size=5, max_size=40),
    st.randoms(use_true_random=False),
)
def test_swap_negates_and_order_does_not_matter(pairs: list[tuple[float, float]], rnd) -> None:  # type: ignore[no-untyped-def]
    base = [p[0] for p in pairs]
    cand = [p[1] for p in pairs]
    forward = paired_delta_ci(base, cand, seed=3, resamples=400)
    backward = paired_delta_ci(cand, base, seed=3, resamples=400)
    assert forward.estimate == pytest.approx(-backward.estimate)
    assert forward.low == pytest.approx(-backward.high) and forward.high == pytest.approx(-backward.low)
    ids = [f"c{i:03d}" for i in range(len(pairs))]
    shuffled = list(range(len(pairs)))
    rnd.shuffle(shuffled)
    rb = make_report({"m": base}, ids=ids)
    rc = make_report({"m": [cand[i] for i in shuffled]}, ids=[ids[i] for i in shuffled])
    comp = compare_metric("m", rb, rc, seed=3, resamples=400)
    comp_sorted = compare_metric("m", rb, make_report({"m": cand}, ids=ids), seed=3, resamples=400)
    assert comp == comp_sorted  # pairs are matched by case id, so file order changes nothing
