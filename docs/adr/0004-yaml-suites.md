# ADR-0004: YAML suites instead of Python-only configuration

- Status: Accepted
- Date: 2026-10-16

## Context

A suite names a dataset, a target, metrics with thresholds, a budget and the splits to run. Suites are read by the CLI, by the composite GitHub Action, by the Promptfoo importer and by people reviewing pull requests. The systems under test are not all Python: an HTTP target can be written in any language, and other tools can consume evalgate's contracts. A suite change should be reviewable as data, validated before anything runs, and fail with a clear location (exit 2) when it is wrong.

## Decision

Suites are YAML files with `schema: evalgate.suite.v1`, validated by the Pydantic model `Suite` in [src/evalgate/contracts/suite.py](../../src/evalgate/contracts/suite.py) and exported to [schemas/evalgate.suite.v1.json](../../schemas/evalgate.suite.v1.json). The committed suites are [evals/suites/classify.yaml](../../evals/suites/classify.yaml), [evals/suites/extract.yaml](../../evals/suites/extract.yaml) and [evals/suites/answer.yaml](../../evals/suites/answer.yaml).

- The loader ([src/evalgate/suite/loader.py](../../src/evalgate/suite/loader.py)) reads YAML with `yaml.safe_load` only, rejects files over 1 MB ([src/evalgate/suite/limits.py](../../src/evalgate/suite/limits.py)), and expands `${VAR}` and `${VAR:-default}` only inside `target`.
- Every model uses `extra="forbid"`, so an unknown or misspelled key fails validation; errors carry a JSON path such as `$.metrics[0].params.actual` and exit with code 2.
- Code stays in Python where it belongs: `target.python` and `target.langgraph` reference `module:callable`, custom metrics register with `@evalgate.metric("name")`, and `plugins` lists modules imported before the run.
- `evalgate schema suite` prints the JSON Schema, so editors and non-Python tools can validate suites.

## Alternatives considered

- **Python-only configuration (rejected).** A suite as a Python module would allow loops, helpers and type checking in the IDE. It was rejected because:
  - Loading it means executing it, so even reading or listing a suite would run arbitrary code; YAML through `safe_load` executes nothing until a `python:` target is called.
  - It cannot be validated against a JSON Schema, diffed as data, or produced by non-Python tools (the Promptfoo importer writes suites; the action takes a suite path).
  - Errors would surface as Python exceptions rather than a path into the document and exit code 2.

## Consequences

### Positive

- One declarative contract shared by the CLI, the action and importers; reviewers see thresholds and budgets change in a plain diff.
- Validation happens before any target or judge call, so a malformed suite costs nothing.
- The schema is versioned with the rest of the contracts and checked for drift by `make schemas`.

### Negative

- YAML has sharp edges (implicit typing, quoting regex patterns such as `"^[a-z_]+$"`); the strict model catches type errors but not every quoting mistake.
- Logic that does not fit `params` must move into a registered custom metric or a plugin module.
- Two invariants live in Pydantic validators, not in the JSON Schema: `target` takes exactly one of `python`, `http` or `langgraph`, and metric names are unique. A tool that validates only against the schema file can accept a suite that `evalgate` rejects.
- Suites remain trusted configuration: a `python:` target runs code when the suite runs.
