# AI-assisted development

evalgate was built with Claude Code from a single build specification, `BUILD.md` (copied to [`docs/specs/000-build-spec.md`](specs/000-build-spec.md)). The specification fixes the product, the architecture, the contracts, a work plan of 46 tasks and the Definition of Done; Claude Code worked through the tasks inside a harness that the repository itself defines and tests. This page describes that harness, the workflow, the guardrails, and what is left for a human. Commit authorship and verification evidence are in [`PROGRESS.md`](../PROGRESS.md) and, after the final verification, `docs/verification.md`.

The build ran in Claude Code on the web (`CLAUDE_CODE_REMOTE=true`); the detected environment is in [`DEVELOPMENT.md`](DEVELOPMENT.md).

## The harness

### Instructions

- [`CLAUDE.md`](../CLAUDE.md) (76 lines): purpose, module map, make targets, conventions (Python 3.12+, ruff, `mypy --strict`, contracts in `src/evalgate/contracts/`, `uv run` for every command, model IDs from configuration, only `llm/gateway.py` imports provider SDKs), testing rules, the commit attribution rule and a never-do list.
- [`AGENTS.md`](../AGENTS.md): the same essentials for any coding agent.
- `.claude/rules/`: 10 rule files. `git-commits.md` applies everywhere; the others load by `paths:` frontmatter: `python.md` (`src/**/*.py`, `scripts/**/*.py`), `frontend.md` (viewer and report templates), `llm-code.md` (`llm/`, `judge/`), `testing.md` (`tests/**`), `evals.md` (`evals/**`, `data/generator/**`), `statistics.md` (`stats/`, `tests/unit/stats/`), `docker.md`, `security.md` and `docs.md`.

### Settings

[`.claude/settings.json`](../.claude/settings.json):

- `attribution` is empty (`"commit": ""`, `"pr": ""`, `"sessionUrl": false`), so Claude Code adds no attribution to commits or pull requests.
- `permissions.allow`: `make *`, `uv run *`, `uv sync *`, `pnpm *`, `docker compose *`, `docker build *`, `git add *`, `git commit *`, `git status`, `git diff *`, `git log *`, `git push -u origin *` and `.tools/bin/*`.
- `permissions.deny`: reading `.env` and `.env.*`, `terraform apply`, `terraform destroy`, `git push --force*`, `git push -f*`, `rm -rf /*` and `rm -rf ~*`. There are no `ask` rules.
- `hooks`: the four hooks below.

### Hooks

The hooks live in `.claude/hooks/` and are tested by `tests/harness/test_hooks.py`.

| Hook | Event and matcher | What it does |
|---|---|---|
| `session_start.sh` | SessionStart | Only when `CLAUDE_CODE_REMOTE=true`, idempotent: starts the Docker daemon with the `mirror.gcr.io` registry mirror, runs `scripts/install_tools.sh`, `uv sync --frozen --all-extras`, creates `.env` from `.env.example` and puts `.tools/bin` on `PATH`. |
| `pre_tool_guard.py` | PreToolUse, `Bash\|Write\|Edit\|MultiEdit\|NotebookEdit` | Blocks the call (exit 2) for the forbidden actions listed below; unreadable hook input is blocked too. |
| `post_edit_format.py` | PostToolUse, `Write\|Edit\|MultiEdit` | Runs `ruff format` and `ruff check --fix` on edited Python files inside the repository; does nothing when ruff is missing. |
| `stop_check.py` | Stop | Runs `make check-fast`; on failure it blocks the stop with the last 15 lines of output. When `stop_hook_active` is true it lets the stop through, so it blocks at most once in a row. |

`pre_tool_guard.py` blocks:

- `terraform apply` and `terraform destroy`;
- identity changes: `git config user.*` writes, `git -c user.*`, and assignments to `GIT_AUTHOR_*` or `GIT_COMMITTER_*`;
- `Co-Authored-By`, `Claude-Session` or "Generated with Claude Code" in commit, tag, notes or merge messages (inline, from `-F` files, from heredocs, or written to `COMMIT_EDITMSG`) and in `gh pr create|edit|comment|review` bodies;
- force pushes (`--force*`, `-f`, `+refspec`, `--mirror`) and tag pushes (`--tags`, `--follow-tags`, `refs/tags/...`, `vX.Y.Z`);
- `gh repo create|edit|delete|fork|rename|archive|unarchive|transfer`, `gh release create|edit|upload|delete`, and `gh api` calls that touch visibility or `user/repos`;
- recursive `rm` of `/` or `~`;
- changes to committed files under `evals/datasets/` and `evals/baselines/` through Write, Edit, redirection, `sed -i`, `perl -i`, `tee`, `truncate`, `rm`, `mv`, `cp`, `install` or `ln` (new versioned files and `MANIFEST.json` are allowed);
- writing `.env` files other than `.env.example`.

### Subagents

Seven subagents in `.claude/agents/`, each with `name`, `description`, `tools` and `model: inherit`:

| Subagent | Tools | Role |
|---|---|---|
| `reviewer` | read-only | Reviews a milestone or the full history against the spec, `CLAUDE.md` and the Definition of Done; ends with "Verdict: ship" or "Verdict: fix first" |
| `security-auditor` | read-only | STRIDE and OWASP Top 10 for LLM applications over the viewer, targets, loader, gateway, judge and PR comment code |
| `stats-reviewer` | read-only | Paired bootstrap, `n`, pairing, multiple comparisons, seeds and the coverage simulation |
| `eval-analyst` | read-only | Checks `evals/reports/*.json` and `evals/REPORT.md` against the §11 thresholds before numbers are quoted |
| `ux-reviewer` | read-only | Viewer and HTML report: tokens, four states, WCAG 2.2 AA, 375 px layout, focus |
| `test-designer` | can write | Designs failing tests first, including Hypothesis properties and anti-flake measures |
| `docs-editor` | can write | README, docs, ADRs and changelog; every number cites its command or report |

Read-only means the `tools` list is `Read, Grep, Glob, Bash` with no Write or Edit.

### Skills

Twelve skills in `.claude/skills/<name>/SKILL.md`: `tdd`, `quality-gate`, `eval-report`, `new-adr`, `add-migration` (DuckDB SQL migrations), `add-endpoint` (viewer and toy-target routes), `add-eval-case` (append-only datasets through the seeded generator), `demo-capture` (Playwright screenshots), `release` (local tag only), `add-metric`, `calibrate-judge` and `add-target-adapter`. `tests/harness/test_agents_skills.py` checks that the 7 agents and 12 skills exist with valid frontmatter.

### MCP servers

[`.mcp.json`](../.mcp.json) configures `playwright` (the local `@playwright/mcp` binary, headless, using the preinstalled Chromium in `/opt/pw-browsers`) and `duckdb` (`mcp-server-motherduck` 1.1.0, read-only on `.evalgate/runs.duckdb`). No test depends on either.

## The workflow

- **Tasks.** The spec's work plan has tasks T-01 to T-46 across milestones M0 (harness) to M9 (hardening). [`PROGRESS.md`](../PROGRESS.md) has one row per task with its status and evidence: the command that was run and its result (for example `uv run pytest tests/harness` → 33 passed for T-05). The walking skeleton (T-07: `evalgate run` end to end, store, viewer `/healthz`, image) came before depth was added.
- **Test first.** Each task names a test to write first. The `tdd` skill makes that test fail for the right reason before any implementation, then runs `make check-fast` and `mypy --strict`, records evidence in `PROGRESS.md` and commits once with a Conventional Commit message.
- **Reviews.** At the end of a milestone the `reviewer` subagent (and, where relevant, `security-auditor`, `stats-reviewer` or `ux-reviewer`) reviews the work; blockers are fixed before the milestone is closed. `PROGRESS.md` records M0 to M6 as done and reviewed, and T-07 notes "M0 reviewer blockers fixed". One example of a review finding is in [`DECISIONS.md`](DECISIONS.md): the security review found super-linear backtracking in PII redaction, fixed with bounded patterns and the regression test `test_redaction_is_linear_on_hostile_input`.
- **Decisions.** Choices the spec leaves open are recorded in [`DECISIONS.md`](DECISIONS.md) with alternatives and a reason; architectural ones get an ADR in `docs/adr/`. Gaps go to [`KNOWN_LIMITATIONS.md`](KNOWN_LIMITATIONS.md) instead of being hidden.
- **Numbers.** Eval, calibration and benchmark numbers come only from generated reports; `evals/REPORT.md` is written by `scripts/build_eval_report.py`, and `tests/unit/test_build_report.py` checks that every number in it traces to a report file. See [`evaluation.md`](evaluation.md).

Status: the task table in `PROGRESS.md` is the source of truth. At the time of writing, T-40 (test containers), T-43 (documents), T-44 (release preparation), T-45 (reviews and fixes) and T-46 (final verification) are still open there.

## Guardrails

- **No force pushes and no tag pushes.** Denied in settings and blocked by `pre_tool_guard.py`; only the current branch is pushed, with `git push -u origin <branch>`. Tags are created locally and pushed by the maintainer.
- **Commit identity.** Every commit is authored and committed by the maintainer; the agent never changes `git config user.*` or `GIT_*` identity variables, and no commit or pull request carries Claude attribution (settings `attribution` plus the guard). `PROGRESS.md` records the identity check made at bootstrap.
- **Append-only data.** Committed files in `evals/datasets/` and `evals/baselines/` are never edited; a change is a new versioned file. Datasets come only from the seeded generator in `data/generator/` (seed 1337), and `MANIFEST.json` hashes are checked by `make seed-data`.
- **Offline tests.** `pytest-socket` blocks non-loopback sockets by default; tests use FakeLLM, FakeJudge, cassettes and in-process HTTP doubles for Langfuse and GitHub, with fixed seeds and random loopback ports. No API key is needed for `make verify`.
- **Never weaken tests.** No skip, xfail or weakened threshold to get green; eval thresholds are only ever raised; nothing is tuned on the `test` split (calibration iterates on `dev`).
- **Never do.** No `terraform apply` or `destroy`, no cloud deployment, no repository creation or visibility change, no messages to real recipients, no secrets or `.env` files in commits.

## What humans still need to do

From the "Needs the maintainer" section of [`PROGRESS.md`](../PROGRESS.md):

- Push the local tag `v0.1.0` once it exists (`git push origin v0.1.0`); this triggers `.github/workflows/release.yml` (see [`runbook.md`](runbook.md#release)).
- Optionally set an `ANTHROPIC_API_KEY` and run `make eval-live` (at most USD 2) to record cassettes and a live calibration; no live numbers exist yet.
- Review 40 of the 200 judge labels in `evals/datasets/judge/answer_correctness.labels.v1.jsonl` and record the reviewed rows with `"source": "maintainer"` in a new `labels.v2` file.

Publishing also depends on settings only the maintainer can make: a PyPI trusted publisher for `release.yml` with the `pypi` environment, and write access to GHCR for the repository owner.
