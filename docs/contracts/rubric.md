# Rubric contract: `evalgate.rubric.v1` and `judge_verdict.v1`

## Purpose

A rubric configures one LLM judge: the prompt file, pointwise or pairwise mode, the scale, the model route, the criteria the judge marks as met or unmet, the calibration thresholds the judge must reach before adoption, and the bias controls. A `judge` metric in a suite points at a rubric file (`params.rubric`). Every judge response must be a `judge_verdict.v1` object; anything else is an error, never a pass. Label rows (`evalgate.label_row.v1`) are the items `evalgate calibrate` measures a rubric against ([ADR-0006](../adr/0006-labels-by-construction.md)).

- JSON Schemas: [schemas/evalgate.rubric.v1.json](../../schemas/evalgate.rubric.v1.json) (`evalgate schema rubric`), [schemas/judge_verdict.v1.json](../../schemas/judge_verdict.v1.json) (`evalgate schema verdict`), [schemas/evalgate.label_row.v1.json](../../schemas/evalgate.label_row.v1.json) (`evalgate schema label`).
- Source of truth: `Rubric`, `RubricThresholds`, `JudgeVerdict` and `LabelRow` in [src/evalgate/contracts/judge.py](../../src/evalgate/contracts/judge.py).
- Rubric files: [evals/rubrics/](../../evals/rubrics/). Prompts: `prompts/judge_*.vN.md`. Rendering and the per-request verdict schema: [src/evalgate/judge/render.py](../../src/evalgate/judge/render.py). Scoring: [src/evalgate/judge/metric.py](../../src/evalgate/judge/metric.py). Calibration: [src/evalgate/judge/calibrate.py](../../src/evalgate/judge/calibrate.py).

## Fields

### Rubric

| Name | Type | Required | Meaning |
|---|---|---|---|
| `schema` | string, constant `evalgate.rubric.v1` | yes | Contract name and version. |
| `name` | string, pattern `^[a-z][a-z0-9_]*$` | yes | Rubric name; label rows name it in `rubric`. |
| `version` | integer at least 1 | yes | Rubric version; the label in reports is `<name>.v<version>`. |
| `mode` | `pointwise` or `pairwise` | yes | Grade one candidate against a reference, or prefer A, B or tie. |
| `scale` | `binary` or `likert5` | yes | Binary scores 1 for `pass` and 0 for `fail`; likert5 uses the verdict's `score`. |
| `prompt` | string | yes | Prompt file, for example `prompts/judge_answer_correctness.v1.md`; its file name (without `.md`) is the `prompt_version` and its SHA-256 goes into the report's `prompt_hashes`. |
| `route` | `judge` or `judge_hard`, default `judge` | no | Model route: `judge` uses `EVALGATE_JUDGE_MODEL` (effort `low`), `judge_hard` uses `EVALGATE_JUDGE_HARD_MODEL` (effort `medium`). |
| `criteria` | array of string, at least 1 | yes | Criteria the judge marks `met` or `unmet`. |
| `thresholds` | object (Thresholds), default all defaults | no | Calibration thresholds for adoption. |
| `position_swap` | boolean, default `true` | no | Judge twice with the order swapped; a verdict that changes with order scores 0.5 and counts as `position_inconsistent`. |
| `verbosity_probe` | boolean, default `true` | no | During calibration, pad candidates with neutral text and measure the score shift. |

### Thresholds

| Name | Type | Required | Meaning |
|---|---|---|---|
| `agreement_min` | number in [0, 1], default 0.8 | no | Minimum share of label rows where the judge agrees with the label. |
| `kappa_min` | number in [-1, 1], default 0.7 | no | Minimum Cohen's kappa. |
| `position_inconsistency_max` | number in [0, 1], default 0.10 | no | Maximum share of items whose verdict changes with order. |
| `verbosity_bias_max` | number in [0, 1], default 0.05 | no | Maximum absolute mean score shift caused by neutral padding. |

### `judge_verdict.v1`

| Name | Type | Required | Meaning |
|---|---|---|---|
| `verdict` | `pass`, `fail`, `A`, `B` or `tie` | yes | The decision; pointwise rubrics use `pass` or `fail`, pairwise rubrics `A`, `B` or `tie`. |
| `score` | number in [0, 1] | yes | The judge's score; used directly for `likert5`. |
| `reasons` | array of string, at most 3, default `[]` | no | Short reasons. |
| `criteria` | map of criterion to `met` or `unmet`, default `{}` | no | Per-criterion result. |

The schema sent to the provider for each request (`verdict_schema` in [src/evalgate/judge/render.py](../../src/evalgate/judge/render.py)) is stricter than the published file: all four fields are required, `verdict` is limited to the rubric's mode, and `criteria` must contain exactly the rubric's criteria. Responses are validated against that schema and the `JudgeVerdict` model.

### Label row (`evalgate.label_row.v1`)

| Name | Type | Required | Meaning |
|---|---|---|---|
| `id` | string | yes | Item ID. |
| `rubric` | string | yes | Rubric name; `evalgate calibrate` scores only rows of the rubric it is given. |
| `split` | `dev` or `test` | yes | `test` for adoption, `dev` for iteration. |
| `input` | string | yes | Task input shown to the judge. |
| `reference` | string | yes | Reference answer. |
| `candidate` | string | yes | Candidate answer (candidate A for pairwise). |
| `candidate_b` | string or null, default null | no | Candidate B for pairwise items. |
| `label` | `0`, `1`, `"A"`, `"B"` or `"tie"` | yes | Expected verdict. |
| `source` | `construction` or `maintainer`, default `construction` | no | Who produced the label. |
| `meta` | object, default `{}` | no | Free-form, for example `construction` and `key_facts`. |

## Minimal valid example

Rubric, from [evals/rubrics/answer_correctness.v1.yaml](../../evals/rubrics/answer_correctness.v1.yaml):

```yaml
schema: evalgate.rubric.v1
name: answer_correctness
version: 1
mode: pointwise
scale: binary
prompt: prompts/judge_answer_correctness.v1.md
route: judge
criteria: [states_key_facts, no_contradiction, answers_question]
thresholds: {agreement_min: 0.80, kappa_min: 0.70, position_inconsistency_max: 0.10, verbosity_bias_max: 0.05}
position_swap: true
verbosity_probe: true
```

The smallest rubric the schema accepts (defaults fill `route`, `thresholds`, `position_swap` and `verbosity_probe`):

```yaml
schema: evalgate.rubric.v1
name: answer_correctness
version: 1
mode: pointwise
scale: binary
prompt: prompts/judge_answer_correctness.v1.md
criteria: [states_key_facts]
```

Verdict, as recorded per case in [evals/baselines/answer.json](../../evals/baselines/answer.json) (`extensions.judge_details`):

```json
{"verdict": "pass", "score": 1.0, "reasons": ["all key facts present"], "criteria": {"states_key_facts": "met", "no_contradiction": "met", "answers_question": "met"}}
```

Label row, the first line of [evals/datasets/judge/answer_correctness.labels.v1.jsonl](../../evals/datasets/judge/answer_correctness.labels.v1.jsonl):

```json
{"id": "jl-001", "rubric": "answer_correctness", "split": "dev", "input": "What are the weekday phone support hours for kitchenware in your retail stores?", "reference": "The kitchenware support team answers calls from 09:00 to 17:00 on weekdays in our retail stores.", "candidate": "The kitchenware support team answers calls from 09:00 to 17:00 on weekdays in our retail stores.", "candidate_b": null, "label": 1, "source": "construction", "meta": {"construction": "exact", "doc_id": "faq-20", "key_facts": ["09:00", "17:00"]}}
```

## Versioning

- The Pydantic models are the source of truth. `uv run python scripts/export_schemas.py` (or `make docs`) regenerates `schemas/`; `make schemas` runs the export with `--check` and fails on drift, as does `tests/contract/test_schemas.py::test_no_drift`.
- Additive changes keep `v1`: a new optional field with a default (for example a new bias control that defaults to off).
- Breaking changes create `evalgate.rubric.v2` or `judge_verdict.v2` with their own schema files: removing or renaming a field, a new required field, or a changed meaning of `score` or `verdict`.
- Two other version numbers are independent of the schema version: a rubric's `version` (bump it when criteria or thresholds change) and the prompt file's `.vN` (bump it instead of editing a released prompt). The prompt version is part of the cache and cassette key, and changed criteria change the request and its `request_digest`, so stale verdicts are not reused. A changed rubric or prompt is re-calibrated before adoption (`make calibrate`).

## Compatibility notes

- Thresholds are only ever raised; never tune a rubric on the `test` split.
- Unknown keys are rejected in all three contracts; extra data in a label row goes under `meta`.
- `evalgate calibrate` exits 1 when a rubric misses any threshold; a judge metric with an uncalibrated rubric (for example one generated by `evalgate import promptfoo`) is imported with `gate: false`.
- Invalid judge output, a refusal or a truncated response makes the metric error for that case; a gated metric with errors fails the gate with reason `error`.
