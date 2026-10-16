"""Percentile bootstrap with numpy ``PCG64``: one-sample means and paired deltas (FR-7)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

DEFAULT_RESAMPLES = 10_000
_MAX_CELLS = 20_000_000  # resamples x n per chunk, bounds memory at 100,000 cases


@dataclass(frozen=True)
class Interval:
    estimate: float
    low: float
    high: float
    n: int
    resamples: int
    seed: int


def _resampled_means(values: np.ndarray, rng: np.random.Generator, resamples: int) -> np.ndarray:
    n = values.shape[0]
    chunk = max(1, min(resamples, _MAX_CELLS // max(n, 1)))
    out = np.empty(resamples, dtype=np.float64)
    done = 0
    while done < resamples:
        k = min(chunk, resamples - done)
        idx = rng.integers(0, n, size=(k, n))
        out[done : done + k] = values[idx].mean(axis=1)
        done += k
    return out


def mean_ci(
    values: Sequence[float] | np.ndarray, seed: int, resamples: int = DEFAULT_RESAMPLES, level: float = 0.95) -> Interval:
    """Percentile CI of the mean of ``values``."""
    arr = np.asarray(values, dtype=np.float64)
    if arr.size == 0:
        return Interval(0.0, 0.0, 0.0, 0, resamples, seed)
    rng = np.random.Generator(np.random.PCG64(seed))
    means = _resampled_means(arr, rng, resamples)
    tail = (1 - level) / 2 * 100
    lo, hi = np.percentile(means, [tail, 100 - tail])
    return Interval(float(arr.mean()), float(lo), float(hi), int(arr.size), resamples, seed)


def paired_delta_ci(
    baseline: Sequence[float],
    candidate: Sequence[float],
    seed: int,
    resamples: int = DEFAULT_RESAMPLES,
    level: float = 0.95,
) -> Interval:
    """Percentile CI of ``mean(candidate - baseline)`` resampling paired cases together."""
    base = np.asarray(baseline, dtype=np.float64)
    cand = np.asarray(candidate, dtype=np.float64)
    if base.shape != cand.shape:
        raise ValueError("paired samples must have the same length")
    return mean_ci(cand - base, seed=seed, resamples=resamples, level=level)
