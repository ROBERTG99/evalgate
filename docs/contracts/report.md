# Report contract: `evalgate.report.v1`

## Purpose

The report is the stable output of `evalgate run`: one JSON document per run with run metadata, per-metric summaries with bootstrap intervals, cost and latency totals, and per-case scores. `evalgate check`, `evalgate report`, `evalgate serve`, the Langfuse exporter and other repositories read it. Non-Python producers may emit it directly; it is the cross-language contract of the gate.

- JSON Schema: [schemas/evalgate.report.v1.json](../../schemas/evalgate.report.v1.json) (also `evalgate schema report`).
- Source of truth: `Report`, `MetricSummary` and `CaseReport` in [src/evalgate/contracts/report.py](../../src/evalgate/contracts/report.py).
- Builder: [src/evalgate/report/build.py](../../src/evalgate/report/build.py). Reports over 50,000,000 bytes are refused by readers ([src/evalgate/suite/limits.py](../../src/evalgate/suite/limits.py)).

## Fields

### Report (top level)

| Name | Type | Required | Meaning |
|---|---|---|---|
| `schema` | string, constant `evalgate.report.v1` | yes | Contract name and version. |
| `suite` | string | yes | Suite name. |
| `run_id` | string | yes | Run ID (UUIDv7 when produced by evalgate). |
| `created_at` | string | yes | UTC timestamp, ISO 8601 with `Z`, seconds precision. |
| `git_sha` | string or null, default null | no | Commit of the code under test. |
| `mode` | `offline` or `live` | yes | `live` when a real judge provider was used. |
| `models` | array of string, default `[]` | no | Models seen in priced steps and judge calls, sorted. |
| `prompt_hashes` | map of string to string, default `{}` | no | Judge prompt version to the SHA-256 of the prompt file. |
| `n_cases` | integer at least 0 | yes | Number of cases in `cases`. |
| `metrics` | map of metric name to MetricSummary | yes | One summary per suite metric. |
| `cost_usd_total` | number at least 0 | yes | Sum of case costs in USD. |
| `cost_usd_per_case` | number at least 0 | yes | `cost_usd_total / n_cases` (0 when there are no cases). |
| `latency_p50_ms` | number at least 0 | yes | Median case latency in milliseconds. |
| `latency_p95_ms` | number at least 0 | yes | 95th percentile case latency in milliseconds. |
| `cases` | array of CaseReport | yes | Per-case results, sorted by `id`. |
| `extensions` | object or null, default null | no | Free-form diagnostics; consumers may ignore it (see below). |

### MetricSummary

| Name | Type | Required | Meaning |
|---|---|---|---|
| `value` | number | yes | Mean of the per-case values (in [0, 1] for built-in metrics). |
| `threshold` | number or null, default null | no | The suite threshold, if any. |
| `direction` | `higher` or `lower`, default `higher` | no | Whether higher is better. |
| `passed` | boolean | yes | `value` meets `threshold` (true when there is no threshold). |
| `ci_low` | number or null, default null | no | Lower bound of the 95% percentile bootstrap interval of the mean. |
| `ci_high` | number or null, default null | no | Upper bound of that interval. |

### CaseReport

| Name | Type | Required | Meaning |
|---|---|---|---|
| `id` | string | yes | Case ID from the dataset; used to pair cases with a baseline. |
| `split` | `dev` or `test` | yes | Dataset split. |
| `scores` | map of metric name to number | yes | Per-case metric values. |
| `passed` | boolean | yes | Whether every gated metric passed its per-case level (`pass_at`) on this case; false when the case errored. |
| `cost_usd` | number at least 0 | yes | Priced cost of the case's steps. |
| `latency_ms` | number at least 0 | yes | Case latency. |
| `error` | string or null, default null | no | Target error after retries; its metrics score their worst value (0, or 1 for `direction: lower`). |

### Extensions written by evalgate

`extensions` is not part of the schema's guarantees, but `evalgate check` reads some keys when they are present ([src/evalgate/stats/gate.py](../../src/evalgate/stats/gate.py)). Keys written by [src/evalgate/runner/engine.py](../../src/evalgate/runner/engine.py):

| Key | Read by the gate | Meaning |
|---|---|---|
| `gates` | yes | Metric name to its suite `gate` flag; without it every metric is gated. |
| `metric_errors` | yes | Metric name to the number of cases whose metric errored; a gated metric with errors fails with reason `error`. |
| `run_health`, `error_rate` | yes | `degraded` when more than 50% of cases errored; fails the gate. |
| `budget` | yes | The suite budget; without it no budget check runs. |
| `split`, `seed`, `resamples` | no | Run settings (bootstrap seed and resample count). |
| `attempts` | no | Case ID to attempts, for cases not done in one attempt. |
| `unpriced_models` | no | Models with tokens but no price in `pricing.yaml`. |
| `cache_hits`, `judge_calls`, `provider_calls`, `judge`, `judge_cost_usd`, `judge_details` | no | Judge diagnostics (suites with judge metrics). |
| `case_tags`, `store_error` | no | Case tags and a run store failure message, when present. |

## Minimal valid example

From [tests/contract/fixtures/report_minimal_producer.json](../../tests/contract/fixtures/report_minimal_producer.json), the fixture that proves a non-Python producer's report is accepted:

```json
{
  "schema": "evalgate.report.v1",
  "suite": "answer",
  "run_id": "0192f3a4-5b6c-7d8e-9f01-23456789abcd",
  "created_at": "2026-10-16T12:00:00Z",
  "git_sha": null,
  "mode": "offline",
  "models": ["toy-model"],
  "prompt_hashes": {},
  "n_cases": 2,
  "metrics": {
    "answer_correctness": {"value": 0.5, "threshold": 0.85, "direction": "higher", "passed": false, "ci_low": 0.0, "ci_high": 1.0}
  },
  "cost_usd_total": 0.002,
  "cost_usd_per_case": 0.001,
  "latency_p50_ms": 120.0,
  "latency_p95_ms": 180.0,
  "cases": [
    {"id": "a-1", "split": "test", "scores": {"answer_correctness": 1.0}, "passed": true, "cost_usd": 0.001, "latency_ms": 100.0, "error": null},
    {"id": "a-2", "split": "test", "scores": {"answer_correctness": 0.0}, "passed": false, "cost_usd": 0.001, "latency_ms": 200.0, "error": null}
  ]
}
```

A report written by evalgate, truncated to one case and part of `extensions`, from [evals/baselines/classify.json](../../evals/baselines/classify.json):

```json
{
  "schema": "evalgate.report.v1",
  "suite": "classify",
  "run_id": "01a14626-55f8-7b34-b98f-c84afdca4850",
  "created_at": "2026-10-16T19:18:01Z",
  "git_sha": "2204384f04102aefcdb2979a59cef112c1303be0",
  "mode": "offline",
  "models": ["toy-model"],
  "prompt_hashes": {},
  "n_cases": 60,
  "metrics": {
    "label_accuracy": {"value": 0.95, "threshold": 0.9, "direction": "higher", "passed": true, "ci_low": 0.8833333333, "ci_high": 1.0},
    "label_format": {"value": 1.0, "threshold": 1.0, "direction": "higher", "passed": true, "ci_low": 1.0, "ci_high": 1.0}
  },
  "cost_usd_total": 0.0043775,
  "cost_usd_per_case": 7.29583e-05,
  "latency_p50_ms": 7.473,
  "latency_p95_ms": 35.778,
  "cases": [
    {"id": "cls-001", "split": "test", "scores": {"label_accuracy": 1.0, "label_format": 1.0}, "passed": true, "cost_usd": 7.1e-05, "latency_ms": 37.452, "error": null}
  ],
  "extensions": {
    "run_health": "ok",
    "error_rate": 0.0,
    "gates": {"label_accuracy": true, "label_format": false},
    "metric_errors": {},
    "budget": {"max_cost_usd": 0.01, "max_p95_ms": 800.0},
    "split": "test",
    "seed": 1337,
    "resamples": 10000
  }
}
```

The truncated document is still valid against the schema, although `n_cases` no longer matches the length of `cases` (the schema does not check that).

## Versioning

- The Pydantic models are the source of truth. `uv run python scripts/export_schemas.py` (or `make docs`) regenerates `schemas/`; `make schemas` runs the export with `--check` and fails on drift, as does `tests/contract/test_schemas.py::test_no_drift`.
- Additive changes keep `v1`: a new optional top-level or nested field with a default, or a new key inside `extensions`.
- Breaking changes create `evalgate.report.v2` with its own `schemas/evalgate.report.v2.json`: removing or renaming a field, making a field required, changing a type, unit or meaning (for example cost currency or latency unit).

## Compatibility notes

- Unknown top-level and nested keys are rejected (`additionalProperties: false`; `tests/contract/test_schemas.py::test_unknown_report_key_rejected`). Producers that need extra data must put it under `extensions`.
- A report without `extensions` is gated on every metric, with no budget, metric-error or run-health checks. Producers that want those checks must write `gates`, `budget`, `metric_errors` and `run_health` as evalgate does.
- Regression checks pair cases by `id`; a baseline and candidate with disjoint IDs give no comparison, and a gated metric then fails closed with reason `error`.
- `created_at`, `run_id` and latencies differ between identical runs; everything else is reproducible offline (NFR-9 measured 0 differences, `evals/reports/bench.json`, `make bench`).
