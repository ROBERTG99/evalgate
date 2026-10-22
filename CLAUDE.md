# CLAUDE.md

evalgate is a Python library and CLI that turns golden sets, deterministic metrics and calibrated
LLM judges into a CI gate. It runs a suite against a Python callable, HTTP endpoint or LangGraph
graph, prices every step, compares with a baseline by paired bootstrap, writes a stable JSON report
(`evalgate.report.v1`) and fails the build on quality, cost or latency regressions.

## Where things live

- Architecture and contracts: `docs/architecture.md`, `docs/contracts/`. Decisions: `docs/DECISIONS.md`. ADRs: `docs/adr/`.
- Known gaps: `docs/KNOWN_LIMITATIONS.md`.

## Module map (`src/evalgate/`)

| Module | Role |
|---|---|
| `contracts/` | Pydantic v2 models; source of truth for `schemas/*.json` |
| `suite/` | YAML suite and JSONL dataset loader, `${VAR:-default}` interpolation in `target` only, size limits |
| `runner/` | asyncio scheduling under a semaphore, timeouts, retries; a failing case never aborts a run |
| `targets/` | `python`, `http` (host allowlist), `langgraph` (one StepRecord per node) |
| `metrics/` | deterministic metrics and the `@evalgate.metric` registry |
| `judge/` | rubric rendering, position swap, verbosity probe, FakeJudge, calibration |
| `llm/gateway.py` | the only module that imports provider SDKs; PII redaction, retries, cassettes |
| `accounting.py`, `budget.py`, `pricing.yaml` | step cost, latency percentiles, budgets |
| `stats/` | paired bootstrap and the gate rule |
| `report/` | report.v1 builder, Markdown and HTML reporters |
| `export/` | Langfuse exporter |
| `store/`, `cache/` | DuckDB run store (migrations, audit chain) and response cache |
| `viewer/` | stdlib `ThreadingHTTPServer` + Jinja2 report viewer |
| `adapters/` | ragas, deepeval metrics and the Promptfoo importer |
| `cli.py` | Typer CLI; exit codes 0 ok, 1 gate failed, 2 invalid input, 3 budget abort, 4 internal, 5 strict export |

Outside the wheel: `examples/toy-targets/` (FastAPI toy systems), `data/generator/` (seeded data),
`scripts/`, `action/` (composite GitHub Action), `evals/`, `prompts/`.

## Make targets

`make bootstrap`, `make up`, `make down`, `make seed`, `make demo`, `make logs`, `make check-fast`,
`make test`, `make test-docker`, `make e2e`, `make eval`, `make eval-live`, `make bench`, `make lint`,
`make typecheck`, `make security`, `make verify`, `make verify-clean`, `make docs`, `make clean`,
`make seed-data`, `make meta-eval`, `make calibrate`, `make record-fixtures`, `make test-extras`,
`make schemas`, `make build`, `make sbom`.

## Conventions

- Python 3.12+, `ruff` (lint and format), `mypy --strict` on `src/`.
- Contracts live in `src/evalgate/contracts/`; after changing one, regenerate `schemas/` with `uv run python scripts/export_schemas.py` (`make schemas` then checks for drift) and commit `schemas/`.
- Use `uv run` for every Python command; dependencies are pinned in `uv.lock`.
- Model IDs come from configuration (`EVALGATE_JUDGE_MODEL`, `EVALGATE_JUDGE_HARD_MODEL`), never from logic.
- Only `src/evalgate/llm/gateway.py` imports `anthropic` or `openai`.
- Conventional Commits (`feat:`, `fix:`, `test:`, `docs:`, `chore:`, `build:`, `ci:`).

## Testing rules

- Write the failing test first, then implement; keep `make check-fast` green between changes.
- Tests are offline: `pytest-socket` blocks non-loopback sockets; use FakeLLM, FakeJudge and cassettes.
- Fixed seeds (`EVALGATE_BOOTSTRAP_SEED=1337`), factories in `tests/factories.py`, random loopback ports,
  no wall-clock assertions under 100 ms.
- Never skip, disable, xfail or weaken a test or a threshold; record gaps in `docs/KNOWN_LIMITATIONS.md`.
- Never tune anything on the `test` split; eval thresholds are only ever raised.

## Commit attribution

Do not add Co-Authored-By, Claude-Session or "Generated with Claude Code" trailers to commits or pull
requests. Do not modify `git config user.*` or the `GIT_AUTHOR_*` / `GIT_COMMITTER_*` variables.

## Never do

- Run `terraform apply` or `terraform destroy`, deploy to a cloud account, or create, publish or change
  the visibility of a GitHub repository.
- Force-push, push tags, or push a branch other than the current one.
- Send messages to real recipients (email, SMS, Slack, voice).
- Commit secrets, `.env` files or real personal data; all data is synthetic.
- Edit committed files in `evals/datasets/` or `evals/baselines/` (add a new versioned file instead).
- Invent metrics, eval scores, benchmark numbers or screenshots: every number cites the command that made it.
