# Action contract: `action/action.yml`

## Purpose

The composite GitHub Action runs a suite in CI, gates it against a baseline, writes the Markdown report to the job summary, upserts one pull request comment per suite and fails the job when the gate fails (FR-9). Its inputs, outputs and comment markers are a public contract for workflows that use `ROBERTG99/evalgate/action@<ref>`. Why it is a composite action is recorded in [ADR-0005](../adr/0005-composite-action.md).

- Definition: [action/action.yml](../../action/action.yml). There is no JSON Schema file for the action; GitHub validates the inputs it declares, and evalgate validates the suite (`evalgate.suite.v1`), report (`evalgate.report.v1`) and check result (`evalgate.check.v1`) it handles.
- PR comment upsert: [scripts/pr_comment.py](../../scripts/pr_comment.py).
- Self-test: [.github/workflows/action-selftest.yml](../../.github/workflows/action-selftest.yml) (toy v1 must pass, toy v2 must fail).

## Inputs

All inputs are strings, as for every GitHub Action.

| Name | Required | Default | Meaning |
|---|---|---|---|
| `suite` | yes | none | Path to the suite YAML (`evalgate.suite.v1`). |
| `baseline` | no | `""` | Baseline `evalgate.report.v1` JSON for paired-bootstrap regression checks; empty means threshold and budget checks only. |
| `report-md` | no | `evalgate-report.md` | Where to write the Markdown report. |
| `split` | no | `test` | Dataset split to run (`dev` or `test`). |
| `max-regression-pp` | no | `"1.0"` | Allowed drop in percentage points before a significant regression fails the gate. |
| `python-version` | no | `"3.13"` | Python version passed to `actions/setup-python@v5`. |
| `extras` | no | `""` | Comma-separated evalgate extras to install, for example `anthropic,langgraph`. |
| `comment` | no | `"true"` | Upsert one PR comment with the report (`true` or `false`); only on `pull_request` events. |
| `github-token` | no | `${{ github.token }}` | Token used to comment; needs `pull-requests: write`. |

## Outputs

| Name | Meaning |
|---|---|
| `passed` | `"true"` when `evalgate check` exited 0, otherwise `"false"`. |
| `report-json` | Path of the `evalgate.report.v1` JSON (`$RUNNER_TEMP/evalgate-report.json`). |
| `check-json` | Path of the `evalgate.check.v1` JSON (`$RUNNER_TEMP/evalgate-check.json`). |

## Steps and exit behaviour

1. Set up Python with `python-version`.
2. Install evalgate from `${{ github.action_path }}/..` (the action's own commit) with `extras`.
3. `evalgate run <suite> --split <split> --out $RUNNER_TEMP/evalgate-report.json`. A non-zero exit here (2 invalid input, 3 budget abort, 4 internal) fails the job immediately.
4. `evalgate check ... --max-regression-pp <pp> --out-json $RUNNER_TEMP/evalgate-check.json --format github` (plus `--baseline` when set), then `evalgate report ... --md <report-md>`; the Markdown is appended to `$GITHUB_STEP_SUMMARY`. If the Markdown cannot be rendered the step exits 4.
5. On `pull_request` events with `comment: true`, upsert the PR comment (below).
6. If `evalgate check` exited non-zero, the last step exits with that code (see [check.md](check.md) for the codes).

## PR comment markers

[scripts/pr_comment.py](../../scripts/pr_comment.py) keeps exactly one comment per suite on a pull request:

| Marker | Where | Meaning |
|---|---|---|
| `<!-- evalgate:report -->` | First line of the body (prepended if missing) | Identifies an evalgate report comment. |
| `<!-- evalgate:suite=<name> -->` | Last line of the body | Identifies the suite; `<name>` is the suite file name without `.yaml`. |

- An existing comment is edited only if it contains both markers and its author is the bot (`user.login` equal to `github-actions[bot]`, or `EVALGATE_COMMENT_AUTHOR`, and `user.type` equal to `Bot`), so a pasted marker in someone else's comment is ignored. Otherwise a new comment is created.
- The body is cut at 60,000 characters (`MAX_BODY`; GitHub's limit is 65,536).
- A 403 (fork pull requests, missing `pull-requests: write`), any other HTTP error or an unreachable API skips the comment with a `::warning` and never changes the gate result.
- The API base comes from `GITHUB_API_URL` (default `https://api.github.com`), the token from `GITHUB_TOKEN`.

## Minimal valid example

From [.github/workflows/evals.yml](../../.github/workflows/evals.yml), reduced to one suite:

```yaml
jobs:
  evals:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      pull-requests: write
    steps:
      - uses: actions/checkout@v4
      - name: Gate the classify suite
        uses: ROBERTG99/evalgate/action@v0.1.0
        with:
          suite: evals/suites/classify.yaml
          baseline: evals/baselines/classify.json
          report-md: evalgate-classify.md
          max-regression-pp: "1.0"
```

Inside this repository the same step uses `uses: ./action`. The suite's target must be reachable from the job (the repository's workflows start the toy targets first).

## Versioning

- The action is versioned with the library: a ref such as `v0.1.0` pins both, because the action installs evalgate from its own commit.
- Additive changes keep the contract: a new optional input with a default that preserves current behaviour, or a new output.
- Breaking changes need a new major version of the action and library: removing or renaming an input or output, changing a default's behaviour, or changing the comment markers (old comments would no longer be found and a second comment would appear).
- The contracts the action reads and writes follow their own rules; `make schemas` fails on drift of their schema files.

## Compatibility notes

- The action needs `bash`, `actions/setup-python` and network access to install packages; it does not use `uv.lock`, so dependency versions resolve within the ranges in `pyproject.toml`.
- `passed` is `"false"` for any non-zero `evalgate check` exit, not only for a gate failure.
- On `push` and other non-`pull_request` events the comment step is skipped; the report is still in the job summary.
- The `passed` output is set only when the check step runs; if `evalgate run` fails, the job fails before any output is written.
