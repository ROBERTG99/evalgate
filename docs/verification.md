# Verification

Final verification of the build specification (§19 of [`specs/000-build-spec.md`](specs/000-build-spec.md)), run on 2026-10-17.

| Item | Value |
|---|---|
| Commit verified | `db4ed367c8446f0da3119dc4fd87ddc926b0dd18` (2026-10-17T00:32:19Z), branch `claude/build-md-execution-a0v4kj` |
| Later commits | Documentation only: this file, `PROGRESS.md`, and `git mv -f BUILD.md docs/specs/000-build-spec.md` |
| Environment | Claude Code on the web; Linux 6.18.44 x86_64; Python 3.13.16; uv 0.11.32; Docker 29.8.2, Compose 5.6.0 (details in [`DEVELOPMENT.md`](DEVELOPMENT.md)) |
| Provider keys | None set (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, AWS credentials absent); no `.env` file in the clone |

## Step 1: fresh clone, `make bootstrap && make verify`

`make verify-clean` (`scripts/verify_clean.sh`) cloned the commit into `/tmp/verify-evalgate/repo`, removed `.env`, unset every provider, cloud, Langfuse, OTel and evalgate variable, set `EVALGATE_LLM_PROVIDER=fake` and ran `make bootstrap verify`.

| Command (inside `make verify`) | Result |
|---|---|
| `make bootstrap` | `uv sync --frozen --all-extras` and pinned tools installed |
| `make lint` | `lint: clean` (ruff, markdownlint, shellcheck, hadolint, actionlint) |
| `make typecheck` | `Success: no issues found in 65 source files` |
| `make schemas` | `schemas: 9 files checked`; OpenAPI up to date |
| `make security` | gitleaks `no leaks found`; bandit no medium or high; pip-audit clean apart from the two documented `[ragas]` findings; `licenses: 198/198 packages allowed`; trivy no high or critical on either image; `security: clean` |
| `make test` | `359 passed`; coverage 87.98% overall, every core package ≥ 85% |
| `make test-extras` | `3 passed` (ragas, deepeval, langgraph) |
| `make eval` | classify, extract and answer PASS; bootstrap coverage 0.9600; three rubrics calibrated PASS; meta-eval 30/30 detected, 0/20 false positives; `all thresholds met` |
| `make bench` | `all budgets met` |
| `make build` | wheel `evalgate-0.1.0-py3-none-any.whl` 118,775 bytes (limit 1,000,000) |
| **Total** | `verify-clean: passed in 310 s at db4ed36` (exit 0, 313 s with the clone) |

## Step 2: the stack in the clone

| Command | Result | Duration |
|---|---|---|
| `docker compose up -d --wait` | toy-targets and report-viewer healthy | 14 s |
| `make seed` | 6 reports: v1 thresholds met, v2 thresholds missed | 15 s |
| `make demo` | v2 `evalgate check exited 1` (label_accuracy -16.67 pp, 95% CI [-26.67, -8.33]); v1 `exited 0` ([`demo-transcript.txt`](demo-transcript.txt)) | 5 s |
| `make e2e` | `6 passed` (axe on every page and on the HTML report in both themes at 375 and 1280 px, 375 px overflow, keyboard focus, filters without JavaScript, screenshots) | 18 s |
| `make test-docker` | unit, integration, contract and harness tests in the test image against real WireMock; E2E `6 passed` in the Playwright image; promtool `SUCCESS`; `test-docker: passed` | 338 s |
| `docker compose down -v` | stack and volumes removed | 11 s |

An earlier attempt of step 2 (at `e7835be`) failed in `make test-docker`: first the disk allowance ran out during the image build (fixed by pruning the Docker build cache), then two container-only gaps showed up and were fixed in `d932b1d`: the README images are not in the test image (now mounted), and the e2e image lacked evalgate for the HTML-report axe test (now installed from `uv.lock`).

## Step 3: reviews

The `reviewer` subagent ran over the whole history (`git diff $(git rev-list --max-parents=0 HEAD)..HEAD`) together with security, statistics, UX and code reviews. Every blocker was fixed with a regression test; the last reviewer pass, at `c5a14cd`, ended with `Verdict: ship`. Findings and evidence are in the T-45 row of [`PROGRESS.md`](../PROGRESS.md); what was not fixed is in [`KNOWN_LIMITATIONS.md`](KNOWN_LIMITATIONS.md).

## Step 4: live evals

No provider key was set, so `make eval-live` was not run against a model: `evals/reports/live-eval.json` records `ran: false` ("ANTHROPIC_API_KEY not set") and [`evals/REPORT.md`](../evals/REPORT.md) states that live evals were not run.

## Authorship check

`git log --format='%an <%ae> | %cn <%ce>' | sort -u` at `e7835be` and again at the final commit:

```text
ROBERTG99 <54124633+ROBERTG99@users.noreply.github.com> | ROBERTG99 <54124633+ROBERTG99@users.noreply.github.com>
```

`git log --format=%B | grep -E 'Co-Authored-By|Claude-Session|Generated with Claude Code'` printed nothing (exit status 1).
