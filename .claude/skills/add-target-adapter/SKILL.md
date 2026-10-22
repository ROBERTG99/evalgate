---
name: add-target-adapter
description: Add a new target kind to evalgate (beside python, http and langgraph) in src/evalgate/targets/, with its contract in src/evalgate/contracts/suite.py. Use when suites must call a new kind of system under test.
---

# Add a target adapter

A target is `async def target(case_input: dict) -> TargetResult` with `TargetResult(output, steps: list[StepRecord], cost_usd, latency_ms, trace_id)`. The suite's `target` key takes exactly one kind. The runner in `src/evalgate/runner/` handles the semaphore, per-case timeout and retries; the adapter only makes one call.

## Steps

1. Specify the kind: its YAML shape under `target:` (for example `grpc: {url, method, timeout_s}`), which fields allow `${VAR:-default}` interpolation, the error mapping (timeouts, connection errors, 408, 429 and 5xx are retriable), and how `StepRecord`s are produced (`kind`, `model`, tokens, cost, `status`).
2. Write the failing tests: `tests/unit/targets/test_<kind>.py` (success, error mapping, retriable vs not, one StepRecord per step) and a loader test in `tests/unit/suite/test_loader.py` that rejects an unknown field with exit 2. Use a random loopback port or an in-process fake; no external network.
3. Run them and watch them fail: `uv run pytest tests/unit/targets tests/unit/suite -x`.
4. Add the contract in `src/evalgate/contracts/suite.py`: a Pydantic v2 model with `extra="forbid"`, added to the "exactly one of" target union. Export the schemas:

   ```bash
   uv run python scripts/export_schemas.py   # regenerate schemas/
   make schemas                              # then confirm there is no drift
   ```

   and commit `schemas/evalgate.suite.v1.json` (the drift test in `tests/contract/test_schemas.py` must pass).
5. Implement `src/evalgate/targets/<kind>.py` and register it in the target factory. Sync callables run in a worker thread. Network adapters enforce `EVALGATE_HTTP_ALLOWED_HOSTS` (SSRF) like `src/evalgate/targets/http.py`. Optional heavy dependencies go behind an extra in `pyproject.toml` and tests marked `extras`.
6. Run `make check-fast`, `uv run mypy --strict src/evalgate` and, for an extra, `make test-extras`.
7. Run the `security-auditor` subagent if the adapter opens sockets or runs code.
8. Document the kind in `docs/contracts/suite.md` with an example suite.

## Done when

- A suite using the new kind loads, runs offline against a fake and writes a valid `evalgate.report.v1`.
- Timeouts and retriable errors are handled by the runner, and a failing call scores 0 without aborting the run.
- `make schemas` shows no drift and the adapter is listed in `docs/contracts/suite.md`.
