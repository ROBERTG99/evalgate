---
name: tdd
description: Test-driven loop for one evalgate task from the build spec work plan (T-NN). Use whenever you implement a task, fix a bug or add behaviour under src/evalgate/, examples/ or scripts/.
---

# TDD loop for one task

Every task in §8 of `docs/specs/000-build-spec.md` (or `BUILD.md`) names its "Test first". That test must exist and fail before any implementation.

## Steps

1. Read the task in §8 (files, test first, done when, depends on) and its FR or NFR in §3; confirm every dependency is checked in `PROGRESS.md`.
2. Design the tests. For anything beyond a single test, run the `test-designer` subagent; otherwise write the named test yourself in the right layer (`tests/unit/<module>/`, `tests/integration/`, `tests/contract/`, `tests/e2e/`), using `tests/factories.py`, fixed seeds and random loopback ports.
3. Run it and watch it fail for the right reason:

   ```bash
   uv run pytest tests/unit/stats/test_bootstrap.py::test_seeded_identical -x
   ```

   An `ImportError` or fixture error is not a valid failure; fix the test until it fails on the missing behaviour.
4. Implement the smallest change under `src/evalgate/` that makes it pass. Keep provider SDK imports in `src/evalgate/llm/gateway.py` only and model IDs in configuration.
5. Re-run the test, then the module's suite: `uv run pytest tests/unit/<module> -q`.
6. If you touched `src/evalgate/contracts/`, regenerate `schemas/` with `uv run python scripts/export_schemas.py` (`make schemas` then checks for drift) and include the updated files.
7. Run `make check-fast` (ruff and unit tests, under 60 s) and `uv run mypy --strict src/evalgate`; both must be green.
8. Refactor with the tests green; re-run `make check-fast`.
9. Record evidence in `PROGRESS.md` under the task: the command and a one-line result, for example `make check-fast -> 212 passed in 18.4s`.
10. Commit once with a Conventional Commit message (`feat:`, `fix:`, `test:` ...), without attribution trailers.

## Rules

- Never skip, xfail, delete or weaken a test or threshold to get green; fix the code or record the gap in `docs/KNOWN_LIMITATIONS.md`.
- Tests stay offline: `pytest-socket` on, FakeLLM, FakeJudge and cassettes in `tests/fixtures/llm/`.
- No wall-clock assertions under 100 ms.
