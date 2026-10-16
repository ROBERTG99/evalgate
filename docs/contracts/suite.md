# Suite contract: `evalgate.suite.v1`

## Purpose

A suite is a YAML file that tells `evalgate run` what to evaluate: the dataset, the target system, the metrics with their thresholds and gate flags, the budget and the splits. It is the input of the CLI and of the composite action. Why suites are YAML and not Python is recorded in [ADR-0004](../adr/0004-yaml-suites.md).

- JSON Schema: [schemas/evalgate.suite.v1.json](../../schemas/evalgate.suite.v1.json) (also `evalgate schema suite`).
- Source of truth: the Pydantic models `Suite`, `TargetSpec`, `HttpTargetSpec`, `MetricSpec` and `BudgetSpec` in [src/evalgate/contracts/suite.py](../../src/evalgate/contracts/suite.py).
- Loader: [src/evalgate/suite/loader.py](../../src/evalgate/suite/loader.py) (YAML through `yaml.safe_load`, `${VAR}` and `${VAR:-default}` expanded only inside `target`, files over 1,000,000 bytes rejected).

Every object rejects unknown keys (`extra="forbid"`, `additionalProperties: false` in the schema). A validation error exits with code 2 and names the JSON path, for example `$.metrics[0].params.actual`.

## Fields

### Suite (top level)

| Name | Type | Required | Meaning |
|---|---|---|---|
| `schema` | string, constant `evalgate.suite.v1` | yes | Contract name and version. |
| `name` | string, pattern `^[a-z0-9][a-z0-9_.-]*$`, at most 64 characters | yes | Suite name; becomes `suite` in the report and the PR comment marker. |
| `description` | string or null | no | Free text for people. |
| `dataset` | string, non-empty | yes | Path to a JSONL dataset (`evalgate.dataset_row.v1` rows). Relative paths resolve against the working directory first, then the suite's folder. |
| `target` | object (Target) | yes | The system under test; exactly one kind. |
| `concurrency` | integer, 1 to 256, default 8 | no | Cases run at once under an asyncio semaphore. |
| `metrics` | array of Metric, at least 1 | yes | Metrics to score; names must be unique. |
| `budget` | object (Budget) or null | no | Cost and latency limits checked by `evalgate check`. |
| `splits` | array of `dev` or `test`, default `[dev, test]` | no | Splits this suite may run. |
| `plugins` | array of string, default `[]` | no | Python modules imported before the run, for example to register custom metrics. |

### Target

Exactly one of the three keys must be set (enforced by a model validator, not by the JSON Schema).

| Name | Type | Required | Meaning |
|---|---|---|---|
| `python` | string `module:callable`, pattern `^[A-Za-z_][\w.]*:[A-Za-z_]\w*$` | one of three | A Python callable (sync callables run in a worker thread). |
| `http` | object (HTTP target) | one of three | An HTTP endpoint; the host must be allowed by `EVALGATE_HTTP_ALLOWED_HOSTS`. |
| `langgraph` | string `module:graph`, same pattern | one of three | A LangGraph graph; one step record per node (needs the `langgraph` extra). |

### HTTP target

| Name | Type | Required | Meaning |
|---|---|---|---|
| `url` | string, non-empty | yes | Endpoint URL; may use `${VAR:-default}`. |
| `method` | `GET`, `POST` or `PUT`, default `POST` | no | HTTP method. |
| `headers` | map of string to string, default `{}` | no | Request headers. |
| `timeout_s` | number, greater than 0 and at most 600, default 30.0 | no | Per-request timeout in seconds. |

### Metric

| Name | Type | Required | Meaning |
|---|---|---|---|
| `name` | string, pattern `^[a-z][a-z0-9_]*$`, at most 64 characters | yes | Metric name; key in the report's `metrics` and `scores`. |
| `kind` | `exact`, `json_schema`, `numeric_tolerance`, `tool_calls`, `contains_all`, `regex`, `judge` or `custom` | yes | Metric implementation. |
| `params` | object, default `{}` | no | Kind-specific parameters (open object; see below). |
| `threshold` | number or null, default null | no | Suite-level threshold on the metric's mean; null means no threshold. |
| `direction` | `higher` or `lower`, default `higher` | no | Whether higher values are better. |
| `gate` | boolean, default `true` | no | Whether the metric can fail the gate (threshold, error and regression checks). |

Common `params` keys, as read by [src/evalgate/metrics/builtin.py](../../src/evalgate/metrics/builtin.py), [src/evalgate/judge/metric.py](../../src/evalgate/judge/metric.py) and [src/evalgate/metrics/registry.py](../../src/evalgate/metrics/registry.py). Selectors are dotted paths rooted at `input`, `output`, `expected` or `meta`.

| Kind | Keys |
|---|---|
| all kinds | `pass_at`: per-case pass level (default 1.0; 0.5 for `custom`). |
| `exact` | `actual` (default `output`), `expected` (default `expected`), `normalize`, `skip_missing`. |
| `json_schema` | `actual` (default `output`), and `schema` (inline) or `schema_path`. |
| `numeric_tolerance` | `actual`, `expected`, `abs_tol`, `rel_tol`. |
| `contains_all` | `actual`, `expected` (or `values`), `case_insensitive` (default true). |
| `regex` | `pattern` (required), `actual`, `flags` (`i` for case-insensitive), `skip_missing`. |
| `tool_calls` | `actual` (default `output.steps`), `expected` (default `expected.tools`), `exact_sequence`. |
| `judge` | `rubric` (required, path to an `evalgate.rubric.v1` file), `candidate` (default `output.answer`), `reference` (default `expected.answer`), `input` (default `input`), `candidate_b` (pairwise). |
| `custom` | `metric` (registered name, default the metric's `name`; `ragas:<name>` and `deepeval:<name>` load adapters); other keys are passed to the implementation. |

### Budget

| Name | Type | Required | Meaning |
|---|---|---|---|
| `max_cost_usd` | number at least 0, or null | no | `evalgate check` fails with `budget_cost` when `cost_usd_total` exceeds it. |
| `max_p95_ms` | number greater than 0, or null | no | `evalgate check` fails with `budget_p95` when `latency_p95_ms` exceeds it. |

### Dataset row (`evalgate.dataset_row.v1`)

The file named by `dataset` holds one JSON object per line, validated by `Case` in [src/evalgate/contracts/records.py](../../src/evalgate/contracts/records.py) and [schemas/evalgate.dataset_row.v1.json](../../schemas/evalgate.dataset_row.v1.json). Rows are at most 1,000,000 bytes and a dataset at most 100,000 cases.

| Name | Type | Required | Meaning |
|---|---|---|---|
| `id` | string, 1 to 200 characters | yes | Case ID; pairs cases between baseline and candidate. |
| `split` | `dev` or `test` | yes | Partition. |
| `input` | object | yes | Passed to the target. |
| `expected` | object or null, default null | no | Reference values for metrics. |
| `tags` | array of string, default `[]` | no | Filters in the viewer. |
| `meta` | object, default `{}` | no | Free-form; reachable by selectors. |

## Minimal valid example

From [evals/suites/classify.yaml](../../evals/suites/classify.yaml):

```yaml
schema: evalgate.suite.v1
name: classify
description: Support-ticket classification against the toy classify target.
dataset: evals/datasets/toys/classify.v1.jsonl
target:
  http: {url: "${EVALGATE_TOYS_URL:-http://localhost:8110}/classify", method: POST, headers: {X-Toy-Version: "${EVALGATE_TOY_VERSION:-v1}"}, timeout_s: 10}
concurrency: 8
metrics:
  - {name: label_accuracy, kind: exact, params: {actual: output.label, expected: expected.label}, threshold: 0.90, direction: higher, gate: true}
  - {name: label_format, kind: regex, params: {actual: output.label, pattern: "^[a-z_]+$"}, threshold: 1.0, direction: higher, gate: false}
budget: {max_cost_usd: 0.01, max_p95_ms: 800}
splits: [dev, test]
```

The smallest suite the schema accepts:

```yaml
schema: evalgate.suite.v1
name: smoke
dataset: data/smoke.v1.jsonl
target: {python: "my_app.agent:answer"}
metrics:
  - {name: exact_answer, kind: exact}
```

## Versioning

- The Pydantic models are the source of truth. `uv run python scripts/export_schemas.py` (or `make docs`) regenerates `schemas/`; `make schemas` runs the same export with `--check` and fails on drift, as does `tests/contract/test_schemas.py::test_no_drift`. Commit `schemas/` with the model change.
- Additive changes keep `v1`: a new optional field with a default, a new metric `kind`, a new optional `params` key.
- Breaking changes create `evalgate.suite.v2`: removing or renaming a field, making a field required, narrowing a type or pattern, or changing a default's meaning. A v2 model gets its own `schemas/evalgate.suite.v2.json`; the v1 file stays.

## Compatibility notes

- Because unknown keys are rejected, a suite that uses a field added in a later v1 release fails on an older evalgate with exit 2. Pin the evalgate version (or the action ref) that your suites need.
- `params` is an open object in the schema; misspelled `params` keys are not caught by the JSON Schema. Selector keys (`actual`, `candidate`) are validated by the loader.
- Two rules live only in Pydantic validators: exactly one `target` kind, and unique metric names. Validate with `evalgate run` or the models, not with the schema file alone, when those matter.
- Environment interpolation applies only to `target`; `${...}` elsewhere is kept literally.
