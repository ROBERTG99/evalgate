# Check contract: `evalgate.check.v1` and CLI exit codes

## Purpose

`evalgate check <report.json> [--baseline <report.json>]` applies the gate rule to a report and writes the decision as an `evalgate.check.v1` document (`--out-json`, or stdout with `--format json`). It records what was compared, with which seed and resample count, every failure with its reason, and every baseline comparison. The process exit code carries the same decision for CI. The statistics are described in [ADR-0003](../adr/0003-paired-bootstrap.md).

- JSON Schema: [schemas/evalgate.check.v1.json](../../schemas/evalgate.check.v1.json) (also `evalgate schema check`).
- Source of truth: `CheckResult`, `CheckFailure` and `Comparison` in [src/evalgate/contracts/report.py](../../src/evalgate/contracts/report.py).
- Gate rule: [src/evalgate/stats/gate.py](../../src/evalgate/stats/gate.py). Exit codes: [src/evalgate/errors.py](../../src/evalgate/errors.py) and [src/evalgate/cli.py](../../src/evalgate/cli.py).

## Fields

### CheckResult (top level)

| Name | Type | Required | Meaning |
|---|---|---|---|
| `schema` | string, constant `evalgate.check.v1`, default the same | no | Contract name and version (always written by evalgate). |
| `report_sha256` | string | yes | SHA-256 of the candidate report file. |
| `baseline_sha256` | string or null, default null | no | SHA-256 of the baseline file, when one was given. |
| `max_regression_pp` | number | yes | Allowed drop in percentage points (`--max-regression-pp`, default 1.0). |
| `seed` | integer | yes | Bootstrap seed (`EVALGATE_BOOTSTRAP_SEED`, default 1337). |
| `resamples` | integer | yes | Bootstrap resamples (10,000). |
| `passed` | boolean | yes | True when `failures` is empty. |
| `failures` | array of CheckFailure, default `[]` | no | Everything that failed the gate. |
| `comparisons` | array of Comparison, default `[]` | no | One entry per metric present in both reports (gated or not). |

### CheckFailure

| Name | Type | Required | Meaning |
|---|---|---|---|
| `metric` | string | yes | Metric name, or `cost_usd_total`, `latency_p95_ms` or `run_health`. |
| `reason` | `threshold`, `regression`, `budget_cost`, `budget_p95` or `error` | yes | Why the gate failed. |
| `value` | number or null, default null | no | Observed value (see the table below). |
| `threshold` | number or null, default null | no | The limit it was compared with. |
| `delta_pp` | number or null, default null | no | Candidate minus baseline, in percentage points (`regression` only). |
| `ci_low_pp` | number or null, default null | no | Lower bound of the 95% paired-bootstrap interval of the delta, in pp (`regression` only). |
| `ci_high_pp` | number or null, default null | no | Upper bound of that interval, in pp (`regression` only). |

What `value` and `threshold` hold for each reason:

| Reason | When | `value` | `threshold` |
|---|---|---|---|
| `threshold` | A gated metric's mean misses its suite threshold. | Metric mean | Suite threshold |
| `regression` | `delta_pp < -max_regression_pp` and `ci_high_pp < 0` (signs flipped for `direction: lower`). | Candidate mean | Baseline mean |
| `budget_cost` | `cost_usd_total > budget.max_cost_usd`. | `cost_usd_total` | `max_cost_usd` |
| `budget_p95` | `latency_p95_ms > budget.max_p95_ms`. | `latency_p95_ms` | `max_p95_ms` |
| `error` | A gated metric errored on some cases. | Number of errored cases | null |
| `error` | `run_health` is `degraded` (metric `run_health`). | `error_rate` | 0.5 |
| `error` | A gated metric has fewer than 10 paired cases (`MIN_PAIRED`). | Paired cases | 10 |
| `error` | A gated metric is missing from the baseline or has no paired case. | 0 | 10 |

### Comparison

| Name | Type | Required | Meaning |
|---|---|---|---|
| `metric` | string | yes | Metric name. |
| `baseline` | number | yes | Baseline mean over the paired cases. |
| `candidate` | number | yes | Candidate mean over the paired cases. |
| `delta_pp` | number | yes | Mean paired difference, in percentage points. |
| `ci_low_pp` | number | yes | Lower bound of the 95% paired-bootstrap interval, in pp. |
| `ci_high_pp` | number | yes | Upper bound, in pp. |
| `n_paired` | integer at least 0 | yes | Cases present in both reports with a score for the metric. |

## CLI exit codes

Defined in [src/evalgate/errors.py](../../src/evalgate/errors.py); every command maps an `EvalgateError` to its `exit_code` and any other exception to 4 ([src/evalgate/cli.py](../../src/evalgate/cli.py)).

| Code | Constant | Meaning | Raised by |
|---|---|---|---|
| 0 | `EXIT_OK` | Success; for `check`, the gate passed. | Every command. |
| 1 | `EXIT_GATE_FAILED` | The gate failed. | `evalgate check` (any failure), `evalgate calibrate` (thresholds not met), `evalgate gc --verify-audit` (broken audit chain). |
| 2 | `EXIT_INVALID_INPUT` | A suite, dataset, rubric, label file, report or option failed validation (`InvalidInputError`). Command-line usage errors also exit 2. | `run`, `check`, `report`, `calibrate`, `schema` and others. |
| 3 | `EXIT_BUDGET_ABORT` | A live run would exceed, or has exceeded, `LIVE_EVAL_BUDGET_USD`, or a judge model has no price in `pricing.yaml` (`BudgetAbortError`). | `evalgate run` with a live provider. |
| 4 | `EXIT_INTERNAL` | Unexpected internal error; set `EVALGATE_DEBUG=1` for the traceback. | Any command. |
| 5 | `EXIT_STRICT_EXPORT` | An export failed while `--strict` was set (`StrictExportError`). | `evalgate export langfuse --strict`. |

`evalgate run` exits 0 even when metrics miss their thresholds; the decision belongs to `evalgate check`.

## Minimal valid example

From [evals/reports/check-classify.json](../../evals/reports/check-classify.json) (`make eval`), the classify v1 run checked against [evals/baselines/classify.json](../../evals/baselines/classify.json), one comparison shown:

```json
{
  "schema": "evalgate.check.v1",
  "report_sha256": "882a3d0bf4d446b15e3029f2a0ceca53aab740d60ed54e3c43e9078a0e42360c",
  "baseline_sha256": "2a923564342653ed3d303667e2ab68b1001a7c308069e8895862f111936fcb39",
  "max_regression_pp": 1.0,
  "seed": 1337,
  "resamples": 10000,
  "passed": true,
  "failures": [],
  "comparisons": [
    {"metric": "label_accuracy", "baseline": 0.95, "candidate": 0.95, "delta_pp": 0.0, "ci_low_pp": 0.0, "ci_high_pp": 0.0, "n_paired": 60}
  ]
}
```

The smallest document the schema accepts (a check without a baseline):

```json
{"report_sha256": "882a3d0bf4d446b15e3029f2a0ceca53aab740d60ed54e3c43e9078a0e42360c", "max_regression_pp": 1.0, "seed": 1337, "resamples": 10000, "passed": true}
```

## Versioning

- The Pydantic models are the source of truth. `uv run python scripts/export_schemas.py` (or `make docs`) regenerates `schemas/`; `make schemas` runs the export with `--check` and fails on drift, as does `tests/contract/test_schemas.py::test_no_drift`.
- Additive changes keep `v1`: a new optional field with a default, or a new `reason` value (consumers should treat an unknown reason as a failure).
- Breaking changes create `evalgate.check.v2` with its own schema file: removing or renaming a field, changing units (percentage points), or changing the gate rule so the same inputs give a different decision.
- Exit codes are part of the CLI contract; a code's meaning never changes within a major version.

## Compatibility notes

- `failures` are grouped by check (thresholds, metric errors, run health, budgets, then baseline comparisons) and are not sorted by severity.
- `comparisons` includes ungated metrics, so a consumer must not treat every negative `delta_pp` as a failure; only `failures` decides.
- Each `evalgate check` also appends a row to the hash-chained `gate_audit` table in `runs.duckdb` ([ADR-0001](../adr/0001-duckdb.md)); a failure to write it is a warning and never changes the exit code.
- With `--format github`, each failure is also printed as a GitHub `::error` annotation.
