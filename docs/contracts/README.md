# Contracts

evalgate's public contracts are Pydantic v2 models in [src/evalgate/contracts/](../../src/evalgate/contracts/), exported as JSON Schema (draft 2020-12) to [schemas/](../../schemas/). `evalgate schema <name>` prints any of them. Each page below gives the purpose, the schema file, a field table checked against the models, a minimal valid example taken from the repository, the versioning rule and compatibility notes.

| Page | Contract | Schema file | Produced by | Read by |
|---|---|---|---|---|
| [suite.md](suite.md) | `evalgate.suite.v1` (and `evalgate.dataset_row.v1`) | [evalgate.suite.v1.json](../../schemas/evalgate.suite.v1.json), [evalgate.dataset_row.v1.json](../../schemas/evalgate.dataset_row.v1.json) | People, `evalgate import promptfoo` | `evalgate run`, the action |
| [report.md](report.md) | `evalgate.report.v1` | [evalgate.report.v1.json](../../schemas/evalgate.report.v1.json) | `evalgate run`, non-Python producers | `check`, `report`, `serve`, `export langfuse` |
| [check.md](check.md) | `evalgate.check.v1` and CLI exit codes 0 to 5 | [evalgate.check.v1.json](../../schemas/evalgate.check.v1.json) | `evalgate check` | CI, the action |
| [rubric.md](rubric.md) | `evalgate.rubric.v1`, `judge_verdict.v1` (and `evalgate.label_row.v1`) | [evalgate.rubric.v1.json](../../schemas/evalgate.rubric.v1.json), [judge_verdict.v1.json](../../schemas/judge_verdict.v1.json), [evalgate.label_row.v1.json](../../schemas/evalgate.label_row.v1.json) | People, judge providers | Judge metrics, `evalgate calibrate` |
| [cassette.md](cassette.md) | `cassette.v1` | [cassette.v1.json](../../schemas/cassette.v1.json) | The gateway with `EVALGATE_RECORD_CASSETTES=1` | `FakeLLM` |
| [action.md](action.md) | Inputs, outputs and PR comment markers of `action/action.yml` | none (GitHub action metadata) | Workflows | GitHub Actions |

`evalgate.step_record.v1` ([schema](../../schemas/evalgate.step_record.v1.json), `StepRecord` in [src/evalgate/contracts/records.py](../../src/evalgate/contracts/records.py)) is the per-step record targets return and the run store keeps; it has no page of its own. The toy targets' HTTP API is described by the generated OpenAPI document [openapi/toy-targets.json](openapi/toy-targets.json) (`scripts/export_openapi.py`; `make docs` writes it and `make schemas` fails on drift).

## Versioning rule (all contracts)

- The models are the source of truth. After changing one, regenerate with `uv run python scripts/export_schemas.py` (or `make docs`) and commit `schemas/`. `make schemas` runs the export with `--check` and fails on drift, and so does `tests/contract/test_schemas.py::test_no_drift`.
- Additive changes keep `v1`: new optional fields with defaults, new enum values that consumers can treat as unknown.
- Breaking changes create a `v2` model and a new `schemas/<name>.v2.json` beside the v1 file: removed or renamed fields, new required fields, narrowed types, or changed meaning or units.
- Every object rejects unknown keys (`additionalProperties: false`), except the free-form maps (`params`, `extensions`, `meta`, `response`). A document using an additive v1 field is therefore rejected by an older reader; pin the evalgate version that matches your producers.
