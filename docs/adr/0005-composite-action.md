# ADR-0005: A composite GitHub Action instead of a Docker action

- Status: Accepted
- Date: 2026-10-16

## Context

The gate reaches pull requests through a GitHub Action (FR-9): `uses: ROBERTG99/evalgate/action@v0.1.0` runs a suite, checks it against a baseline, writes the Markdown report to the job summary, upserts exactly one PR comment per suite, and fails the job when the gate fails. Users need to choose the Python version and the extras (for example `anthropic` or `langgraph`) that their targets and judges need, and Python targets import code from the user's own checkout, so the gate must run in the same environment as that checkout.

## Decision

Ship a composite action in [action/action.yml](../../action/action.yml). Its steps:

1. `actions/setup-python@v5` with the `python-version` input (default `3.13`).
2. `pip install` evalgate from `${{ github.action_path }}/..`, that is, from the same commit as the action, plus the requested `extras`.
3. `evalgate run` writes the report to `$RUNNER_TEMP/evalgate-report.json`.
4. `evalgate check --format github` (with `--baseline` when given) writes `$RUNNER_TEMP/evalgate-check.json`; `evalgate report` renders the Markdown report into the job summary.
5. On `pull_request` events with `comment: true`, [scripts/pr_comment.py](../../scripts/pr_comment.py) upserts the comment; a 403 or an unreachable API skips the comment with a warning and never changes the gate.
6. A final step exits with the `evalgate check` exit code when it was not 0.

The inputs, outputs and comment markers are documented in [docs/contracts/action.md](../contracts/action.md). [.github/workflows/action-selftest.yml](../../.github/workflows/action-selftest.yml) runs the action on the classify suite and asserts that toy v1 passes and toy v2 fails.

## Alternatives considered

- **Docker container action (rejected).** A Docker action would pin the whole toolchain in an image and give a hermetic environment. It was rejected because:
  - Every run pays an image build or pull before the gate starts; the composite action only installs a small wheel (0.1176 MB, `evals/reports/bench.json`) and its dependencies.
  - GitHub runs Docker container actions only on Linux runners; the composite action runs where `actions/setup-python` and `bash` are available.
  - A container is isolated from the job's Python environment, so `python:` and `langgraph:` targets that import the user's packages, and user-selected extras, would need a custom image or extra mounting. The composite action installs into the job's own Python.
  - The release would have to publish and version an image in step with the library; the composite action installs the library from the action's own commit, so the action ref and the library version cannot drift.

## Consequences

### Positive

- No image registry in the critical path; the action ref pins both the action and the library.
- Users pick the Python version and extras per workflow.
- The repository's own `evals` workflow gates through `uses: ./action`, so the action is exercised on every pull request ([.github/workflows/evals.yml](../../.github/workflows/evals.yml)).

### Negative

- Every run installs evalgate and its dependencies with `pip`; the action has no built-in dependency cache, and the install time was not measured.
- The environment is less hermetic than an image: dependency versions resolve at install time within the ranges in `pyproject.toml`, not from `uv.lock`.
- The steps use `bash`, so runners without `bash` are not supported.
- Fork pull requests usually lack `pull-requests: write`; the comment is skipped there, and the result is only in the job summary and the job status.
