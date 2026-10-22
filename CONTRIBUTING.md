# Contributing

Thanks for helping. This page is the short version; [`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md) has the environment details and [`CLAUDE.md`](CLAUDE.md) and [`.claude/rules/`](.claude/rules/) hold the conventions that contributors and AI coding assistants follow.

## Setup

```bash
make bootstrap   # uv sync --all-extras, pinned tools in .tools/bin, .env from .env.example
make check-fast  # ruff and unit tests, under a minute
```

No API key is needed: every test, the demo and `make verify` run offline with FakeLLM, FakeJudge, cassettes and the toy targets.

## Workflow

1. Open an issue or describe the change in the pull request.
2. Write the failing test first, named after the behaviour (`test_timeout_scores_zero`).
3. Make it pass; keep `mypy --strict` and ruff clean (`make typecheck`, `make lint`).
4. Run `make verify` before asking for review; `make test-docker` and `make e2e` when you touched the viewer, the images or the compose stack.
5. Use [Conventional Commits](https://www.conventionalcommits.org/) (`feat(judge): ...`, `fix(stats): ...`).

## Rules checked in review

- Never skip, xfail or weaken a test or threshold to get green; fix the code or document the gap in [`docs/KNOWN_LIMITATIONS.md`](docs/KNOWN_LIMITATIONS.md).
- Datasets and baselines are append-only: add `*.vN.jsonl` or a new baseline file; never edit a committed one.
- Never tune prompts, rules or thresholds on the `test` split; thresholds only go up.
- Only `src/evalgate/llm/gateway.py` imports provider SDKs; prompts are versioned files in `prompts/`.
- Every number in the docs cites the command or report that produced it.
- Contract changes are additive within `v1`; `make schemas` fails on drift.
- Decisions go in [`docs/DECISIONS.md`](docs/DECISIONS.md); architectural ones get an ADR in [`docs/adr/`](docs/adr/README.md).

## Pull requests

CI must be green (`ci`, `e2e`, `evals`, `docker`). The `evals` job gates the toy suites through the action and comments the deltas on the pull request.
