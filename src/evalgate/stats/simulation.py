"""Coverage simulation of the paired percentile bootstrap (used by tests and ``make eval``)."""

from __future__ import annotations

from typing import Any

import numpy as np

from evalgate.stats.bootstrap import paired_delta_ci


def coverage(
    n_datasets: int = 400,
    n_cases: int = 150,
    p_base: float = 0.85,
    p_cand: float = 0.80,
    correlation: float = 0.6,
    resamples: int = 10_000,
    seed: int = 1337,
    continuous: bool = False,
) -> dict[str, Any]:
    """Share of 95% CIs that contain the true delta over simulated paired binary datasets.

    Each case has a latent difficulty shared by both runs (``correlation``), so the pairs are correlated
    as they are in real regressions. The true delta is estimated from 2,000,000 simulated pairs.
    """
    rng = np.random.Generator(np.random.PCG64(seed))

    def draw(n: int) -> tuple[np.ndarray, np.ndarray]:
        shared = rng.random(n)
        own_b, own_c = rng.random(n), rng.random(n)
        u_b = np.where(rng.random(n) < correlation, shared, own_b)
        u_c = np.where(rng.random(n) < correlation, shared, own_c)
        if continuous:  # graded scores in [0, 1] (e.g. likert judges, string similarity)
            return np.clip(u_b + p_base - 0.5, 0, 1), np.clip(u_c + p_cand - 0.5, 0, 1)
        return (u_b < p_base).astype(float), (u_c < p_cand).astype(float)

    if continuous:
        big_b, big_c = draw(2_000_000)
        truth = float(big_c.mean() - big_b.mean())
    else:
        truth = p_cand - p_base  # each marginal is uniform, so the true delta is exact
    hits = 0
    widths = []
    for i in range(n_datasets):
        b, c = draw(n_cases)
        ci = paired_delta_ci(b, c, seed=seed + i, resamples=resamples)
        hits += int(ci.low <= truth <= ci.high)
        widths.append(ci.high - ci.low)
    return {
        "n_datasets": n_datasets,
        "n_cases": n_cases,
        "p_base": p_base,
        "p_cand": p_cand,
        "correlation": correlation,
        "resamples": resamples,
        "seed": seed,
        "true_delta": round(truth, 6),
        "coverage": round(hits / n_datasets, 6),
        "mean_ci_width_pp": round(float(np.mean(widths)) * 100, 4),
    }


#: The primary scenario is the §11 check (400 datasets, 10,000 resamples). The others are reported so the
#: regimes where the percentile bootstrap under-covers (small n, near-perfect baselines) stay visible.
SCENARIOS: dict[str, dict[str, Any]] = {
    "primary_n150_binary": {"n_cases": 150, "p_base": 0.85, "p_cand": 0.80},
    "n60_binary": {"n_cases": 60, "p_base": 0.85, "p_cand": 0.80},
    "n60_near_perfect": {"n_cases": 60, "p_base": 0.97, "p_cand": 0.95},
    "n20_binary": {"n_cases": 20, "p_base": 0.85, "p_cand": 0.80},
    "n60_continuous": {"n_cases": 60, "p_base": 0.70, "p_cand": 0.65, "continuous": True},
}


def scenarios(n_datasets: int = 400, resamples: int = 10_000) -> dict[str, dict[str, Any]]:
    return {name: coverage(n_datasets=n_datasets, resamples=resamples, **params) for name, params in SCENARIOS.items()}
