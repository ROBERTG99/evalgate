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
