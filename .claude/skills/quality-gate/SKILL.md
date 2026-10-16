---
name: quality-gate
description: Run evalgate's quality gates in the right order and summarise them as evidence. Use before closing a task or milestone, before asking the reviewer subagent for a verdict, and in final verification.
---

# Quality gate

The single gate is `make verify` (lint, typecheck, schemas, security, test, test-extras, eval, bench, build). Run cheap checks first so failures surface fast.

## Steps

1. Fast loop, after every change:

   ```bash
   make check-fast
   ```

   Ruff check, ruff format `--check` and `pytest tests/unit tests/harness -m "not slow"`; must finish under 60 s.
2. Static checks:

   ```bash
   make lint        # ruff, markdownlint-cli2, shellcheck, hadolint, actionlint
   make typecheck   # mypy --strict src/evalgate
   make schemas     # JSON Schema export, fails on drift in schemas/
   ```

3. Full tests with coverage: `make test` (unit, integration, contract, harness; `scripts/check_coverage.py` enforces ≥ 85% on `suite runner targets metrics judge stats cache store report` and ≥ 70% overall). Then `make test-extras`.
4. Security: `make security` (gitleaks, bandit, pip-audit, `scripts/check_licenses.py`, trivy). Any high or critical finding is fixed or documented with a reason in `docs/security.md`.
5. Evals and performance: `make eval` (writes `evals/REPORT.md`, checks §11 thresholds), `make bench` (NFR budgets), `make build` (wheel under 1 MB).
6. When the stack is up (`make up`): `make e2e` (Playwright and axe); before release, `make test-docker`.
7. Milestone end: run the `reviewer` subagent on the milestone diff; add `stats-reviewer`, `ux-reviewer` or `security-auditor` when their areas changed. Fix every blocker and repeat from step 1.
8. Record evidence in `PROGRESS.md`: each command with a one-line result and duration.

## Rules

- Never pass a gate by skipping, disabling or weakening a check, test or threshold.
- `make verify` must pass with no API keys and no `.env`; `make eval-live` is never part of it.
- Summarise output; do not paste long logs into the conversation.
