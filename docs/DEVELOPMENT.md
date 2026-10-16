# Development

## Environment detected at bootstrap (2026-10-16)

| Item | Value |
|---|---|
| Mode | Claude Code on the web (`CLAUDE_CODE_REMOTE=true`) |
| `uname -srm` | Linux 6.18.44-fc-v139 x86_64 |
| python3 | 3.13.16 |
| uv | 0.11.32 |
| node | v22.22.0 |
| pnpm | 10.28.0 |
| go | go1.24.7 |
| docker | 29.8.2 |
| docker compose | 5.6.0 |
| gh | 2.89.0 |

Docker: the daemon is preinstalled but not running in the cloud container; it is started with the
registry mirror `mirror.gcr.io` (Appendix A of the build spec, automated by `.claude/hooks/session_start.sh`).

## Setup

```bash
make bootstrap   # uv sync --frozen --all-extras, pinned tools into .tools/bin, .env from .env.example
make check-fast  # ruff and unit tests
```

Tool versions are pinned in `tools/versions.env` (hadolint, trivy, shellcheck, actionlint, gitleaks) and `tools/node/package.json` (markdownlint-cli2, `@playwright/mcp`). Go and pnpm are needed only to install actionlint, gitleaks and markdownlint.

## Make targets

| Target | What it does |
|---|---|
| `make up` / `make down` | Start the compose stack with health checks and seed the viewer / stop it |
| `make seed`, `make demo` | Load the synthetic runs into the viewer; run the scripted v2-blocked, v1-passes scenario |
| `make check-fast` | Ruff and unit tests |
| `make test` | Unit, integration, contract and harness tests with coverage gates (85% core packages, 70% overall) |
| `make test-extras` | Tests of the optional extras (ragas, deepeval, langgraph, otel) |
| `make e2e` | Playwright and axe against the running viewer (`EVALGATE_VIEWER_URL`), writes `docs/images/` |
| `make test-docker` | The whole suite in containers, real WireMock, E2E and promtool rule tests |
| `make eval` | Offline evals with the §11 thresholds; writes `evals/reports/*.json` and `evals/REPORT.md` |
| `make eval-live` | Live calibration with a real judge within `LIVE_EVAL_BUDGET_USD` (needs a provider key) |
| `make meta-eval`, `make calibrate` | Meta-evaluation of the gate; judge calibration on the test labels |
| `make bench` | NFR-1 to NFR-9 budgets; writes `evals/reports/bench.json` |
| `make lint`, `make typecheck` | Ruff, markdownlint, shellcheck, hadolint, actionlint; `mypy --strict` |
| `make security` | gitleaks, bandit, pip-audit, license check, trivy on both images |
| `make schemas`, `make docs` | JSON Schema and OpenAPI drift checks; regenerate them and the screenshots |
| `make build`, `make sbom` | Wheel and sdist under 1 MB; CycloneDX SBOM |
| `make seed-data` | Regenerate the synthetic datasets (seed 1337) and check `MANIFEST.json` |
| `make verify`, `make verify-clean` | Everything above that runs offline; the same in a fresh clone |

## Layout

| Path | Contents |
|---|---|
| `src/evalgate/` | The library and CLI (the only code in the wheel) |
| `examples/toy-targets/` | FastAPI toy systems used by the evals and tests (uv workspace member, not shipped) |
| `data/generator/` | Seeded synthetic data generator |
| `evals/` | Suites, datasets, rubrics, schemas, baselines and the generated `REPORT.md` |
| `prompts/` | Versioned judge and toy prompts |
| `schemas/` | Exported JSON Schemas of the contracts |
| `tests/` | `unit`, `integration`, `contract`, `harness` and `e2e` suites |
| `docker/`, `compose*.yaml`, `deploy/` | Images, stacks, collector, Prometheus, Grafana and WireMock mappings |
| `action/` | The composite GitHub Action |
| `.claude/` | Claude Code settings, hooks, rules, subagents and skills |

## Testing notes

- `pytest-socket` is on for every run: only loopback connections are allowed. Use port 0 for servers.
- Tests never call a live provider; they use FakeLLM, FakeJudge, cassettes and response fixtures.
- E2E needs the viewer running (`make up`) and Chromium for Playwright 1.56.0 (preinstalled in `/opt/pw-browsers` in the cloud container; `uv run playwright install chromium` elsewhere).
