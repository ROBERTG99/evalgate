# Verification

Status: **in progress.** The final verification of §19 of the build spec (fresh clone, `make bootstrap && make verify`, the compose scenario, reviews) runs in task T-46 and replaces this page with its full record. Until then this page lists the checks already run on the working tree, each with its command and result.

## Checks run before final verification

Date: 2026-10-16. Commit: `265270e` (85 commits). Environment: Claude Code on the web, Linux 6.18.44 x86_64, Python 3.13.16, uv 0.11.32, Docker 29.8.2 (see [`DEVELOPMENT.md`](DEVELOPMENT.md)). No provider API keys set.

| Command | Result |
|---|---|
| `make test` | 298 passed; coverage 86.56% overall, every core package at or above 85% except `report` (79.10%), fixed by `tests/unit/report/test_render_and_load.py` and to be re-measured in T-46 |
| `make test-docker` | `test-docker: passed` (container tests against real WireMock, E2E 5 passed, promtool SUCCESS) |
| `make demo` against `docker compose up -d --wait` | v2 `evalgate check exited 1`, v1 `exited 0` ([`demo-transcript.txt`](demo-transcript.txt)) |
| `make lint` | `lint: clean` (markdownlint 0 issues in 73 files, shellcheck, hadolint, actionlint) |
| `uv run mypy --strict src/evalgate` | Success: no issues found in 65 source files |

## Authorship check

`git log --format='%an <%ae> | %cn <%ce>' | sort -u` at `265270e`:

```text
ROBERTG99 <54124633+ROBERTG99@users.noreply.github.com> | ROBERTG99 <54124633+ROBERTG99@users.noreply.github.com>
```

`git log --format=%B | grep -E 'Co-Authored-By|Claude-Session|Generated with Claude Code'` printed nothing (exit status 1).
