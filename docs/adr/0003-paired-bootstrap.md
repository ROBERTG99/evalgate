# ADR-0003: Paired percentile bootstrap instead of a paired t-test

- Status: Accepted
- Date: 2026-10-16

## Context

`evalgate check` compares a candidate report with a baseline report on the same cases and must decide whether a drop in a gated metric is a regression or noise (FR-7). The decision fails builds, so it has to be reproducible bit for bit and must not cry wolf on noise.

The per-case scores are bounded in [0, 1] and are usually binary (exact match, regex, judge pass or fail), sometimes three-valued (pairwise judge: 1, 0.5, 0) or continuous (likert judge, custom metrics). Baselines often sit near 1.0: the committed classify baseline has `label_accuracy` 0.95 and `label_format` 1.0 on 60 test cases ([evals/baselines/classify.json](../../evals/baselines/classify.json)). Paired differences are then mostly 0 with a few -1 or +1, and test splits are small (60 cases per toy suite).

## Decision

Use a paired percentile bootstrap ([src/evalgate/stats/bootstrap.py](../../src/evalgate/stats/bootstrap.py)):

- `paired_delta_ci` takes the per-case differences `candidate - baseline` over the cases present in both reports and resamples cases with replacement; the 95% interval is the 2.5th and 97.5th percentile of the resampled means.
- 10,000 resamples (`DEFAULT_RESAMPLES`), numpy `PCG64` seeded with `EVALGATE_BOOTSTRAP_SEED` (default 1337, [src/evalgate/config.py](../../src/evalgate/config.py)). The seed and resample count are written into every `evalgate.check.v1` result.
- The same `mean_ci` gives the per-metric `ci_low` and `ci_high` in `evalgate.report.v1`.

The gate rule ([src/evalgate/stats/gate.py](../../src/evalgate/stats/gate.py)): a gated metric regresses when `delta_pp < -max_regression_pp` and the 95% interval lies entirely below 0 (`ci_high_pp < 0`); signs flip for `direction: lower`. A gated metric with fewer than `MIN_PAIRED = 10` paired cases, or that the baseline cannot speak to, fails closed with reason `error`.

## Alternatives considered

- **Paired t-test (rejected).** It is cheap and familiar, but:
  - It relies on the mean difference being approximately normal. With binary scores, a baseline near 1.0 and 60 cases, the differences are a few nonzero values among many zeros, so the normal approximation is poor, and the t interval can extend past the feasible range of the delta.
  - When every paired difference is 0 (as for both classify metrics in [evals/reports/check-classify.json](../../evals/reports/check-classify.json), interval [0.0, 0.0]) the standard error is 0 and the t statistic is undefined; the bootstrap returns the degenerate interval without a special case.
  - The bootstrap handles binary, three-valued and continuous metrics with one code path, and the same machinery yields the per-metric intervals in the report.
  - It would add `scipy` for the t distribution; the build spec rejects scipy in favour of vectorised numpy (§5).

  No head-to-head simulation of the t-test was run for this decision; the rejection rests on the reasons above, not on a measured comparison.
- **Unpaired comparison of two means (rejected).** It ignores that both runs score the same cases, so case difficulty inflates the variance and real regressions are missed.

## Consequences

### Positive

- Deterministic: the same reports, seed and resample count give the same `evalgate.check.v1` result.
- Measured coverage in simulation: 400 simulated paired datasets of 150 correlated binary cases (true delta -5 pp) gave 95% interval coverage 0.96, inside the 0.92 to 0.98 target, with a mean interval width of 14.1286 pp ([evals/reports/bootstrap-coverage.json](../../evals/reports/bootstrap-coverage.json), `make eval`).
- Cheap enough for CI: comparing 200 cases with 10,000 resamples on 2 metrics took 0.0324 s against a 2 s budget (NFR-8, `evals/reports/bench.json`, `make bench`).
- A real regression is clear: the `make demo` classify drop is -16.67 pp with interval [-26.67, -8.33] ([docs/DECISIONS.md](../DECISIONS.md)).

### Negative

- The percentile bootstrap under-covers at small n. The same simulation measured coverage 0.9375 for 60 binary cases, 0.8875 for 60 cases with a near-perfect baseline (0.97 to 0.95), and 0.8425 for 20 cases ([evals/reports/bootstrap-coverage.json](../../evals/reports/bootstrap-coverage.json)). These scenarios have a real drop, so they measure coverage rather than the false-alarm rate; in the near-perfect regime the misses mostly understate the drop, so the main cost is lower power. At 10 cases, the `MIN_PAIRED` floor, coverage is about 0.68 (same file). Test splits should be larger than 60 when a metric sits near 1.0. A BCa or exact-binomial interval is the next improvement ([docs/KNOWN_LIMITATIONS.md](../KNOWN_LIMITATIONS.md)).
- Each gated metric is tested on its own at 95%; there is no multiple-comparison adjustment ([docs/KNOWN_LIMITATIONS.md](../KNOWN_LIMITATIONS.md)).
- Results depend on the seed; changing `EVALGATE_BOOTSTRAP_SEED` can move an interval bound across 0 for a borderline delta. The seed is therefore fixed and recorded.
