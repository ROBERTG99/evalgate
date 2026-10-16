# AGENTS.md

Instructions for any coding agent working in this repository. `CLAUDE.md` has the full version.

- **What it is:** evalgate, a Python library and CLI that gates CI on eval quality, cost and latency.
- **Setup:** `make bootstrap` (uv, pinned tools in `.tools/bin`). Every Python command runs through `uv run`.
- **Fast loop:** `make check-fast` (ruff and unit tests). Full gate: `make verify`.
- **Contracts:** Pydantic models in `src/evalgate/contracts/`; run `make schemas` after a change.
- **Offline:** tests and `make verify` need no API keys; live calls only through `make eval-live`.
- **Tests first,** never skip or weaken a test or threshold; never tune on the `test` split.
- **Commits:** Conventional Commits, authored by the maintainer only, with no Co-Authored-By,
  Claude-Session or "Generated with Claude Code" trailers. Never change git identity or force-push.
- **Never:** deploy, run `terraform apply`/`destroy`, message real people, commit secrets, or edit
  committed datasets and baselines (add a new version instead).
- **Progress:** `PROGRESS.md`; decisions in `docs/DECISIONS.md`; ADRs in `docs/adr/`.
