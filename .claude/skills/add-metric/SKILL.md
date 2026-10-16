---
name: add-metric
description: Add a deterministic or custom metric to evalgate. Use when a suite needs a new metric kind or a registered custom metric via @evalgate.metric("name") in src/evalgate/metrics/.
---

# Add a metric

A metric implements `class Metric(Protocol): name: str; def score(self, case: Case, result: TargetResult) -> MetricScore` and returns `MetricScore(name, value: float, passed: bool, details: dict)`. Custom metrics register with `@evalgate.metric("name")`.

## Steps

1. Define the behaviour: inputs (selectors rooted at `input`, `output`, `expected` or `meta`), the value range (0 to 1 unless documented), how `passed` is decided, and what goes into `details`. A missing selector or invalid output scores 0 with a reason in `details`; it never raises out of the runner.
2. Write the failing tests in `tests/unit/metrics/test_<name>.py`: examples from the spec, edge cases (empty output, missing key, unicode, huge strings), and at least one Hypothesis property, for example:

   ```python
   @given(st.text())
   @settings(derandomize=True)
   def test_reflexive(s: str) -> None:
       assert score(actual=s, expected=s).value == 1.0
   ```

   For a custom metric, extend `tests/unit/metrics/test_registry.py` as well.
3. Run them and watch them fail: `uv run pytest tests/unit/metrics -x`.
4. Implement in `src/evalgate/metrics/<name>.py`, registering it:

   ```python
   @evalgate.metric("word_budget")
   def word_budget(case: Case, result: TargetResult) -> MetricScore: ...
   ```

   A new built-in `kind` also needs its literal in `src/evalgate/contracts/suite.py`; then run `make schemas` and commit `schemas/evalgate.suite.v1.json`.
5. Keep it pure and deterministic: no I/O, no network, no randomness without a seed. Anything that calls a model belongs to `src/evalgate/judge/`, not here.
6. Run `make check-fast` and `uv run mypy --strict src/evalgate`.
7. Document it in `docs/contracts/suite.md` (params, range, example YAML) and, for a custom-metric example, in `examples/metrics/`.
8. Record evidence in `PROGRESS.md`.
