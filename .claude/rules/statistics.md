---
paths:
  - "src/evalgate/stats/**"
  - "tests/unit/stats/**"
---

# Statistics

- Comparisons are paired: resample case ids present in both runs, never the two runs independently.
- Report the seed, the number of resamples and `n_paired` with every interval.
- 95% percentile intervals from 10,000 resamples of numpy `PCG64(seed)`.
- Each gated metric is one pre-declared hypothesis; do not add post-hoc comparisons to the gate.
- Coverage of the interval is checked by simulation (`tests/unit/stats/test_coverage_sim.py`).
