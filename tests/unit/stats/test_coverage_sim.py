import pytest

from evalgate.stats.simulation import coverage


@pytest.mark.slow
def test_bootstrap_95_ci_coverage_in_range() -> None:
    """400 simulated paired datasets (150 correlated binary cases, true delta -5 pp), 10,000 resamples each."""
    result = coverage(n_datasets=400)
    assert result["n_datasets"] == 400
    assert result["resamples"] == 10_000
    assert 0.92 <= result["coverage"] <= 0.98, result


@pytest.mark.slow
def test_coverage_also_holds_with_no_effect() -> None:
    result = coverage(n_datasets=200, p_base=0.9, p_cand=0.9, seed=7, resamples=4_000)
    assert abs(result["true_delta"]) < 0.002
    assert 0.92 <= result["coverage"] <= 0.98, result


@pytest.mark.slow
def test_small_n_regimes_are_reported_not_hidden() -> None:
    """Percentile intervals under-cover at small n with near-perfect baselines; the numbers are reported
    in evals/REPORT.md and docs/KNOWN_LIMITATIONS.md rather than tuned away."""
    from evalgate.stats.simulation import SCENARIOS, scenarios

    result = scenarios(n_datasets=100, resamples=2_000)
    assert set(result) == set(SCENARIOS)
    for name, r in result.items():
        assert 0.5 < r["coverage"] <= 1.0, name


@pytest.mark.slow
def test_continuous_scores_cover_in_range() -> None:
    """Graded scores (n=60), the `n60_continuous` scenario of evals/REPORT.md, 400 datasets x 10,000 resamples."""
    from evalgate.stats.simulation import SCENARIOS

    result = coverage(n_datasets=400, **SCENARIOS["n60_continuous"])
    assert 0.92 <= result["coverage"] <= 0.98, result
