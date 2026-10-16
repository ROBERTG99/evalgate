---
paths:
  - "src/**/*.py"
  - "scripts/**/*.py"
  - "examples/**/*.py"
  - "data/**/*.py"
  - "tests/**/*.py"
---

# Python

- Python 3.12+, type hints everywhere; `src/` passes `mypy --strict`.
- Format and lint with ruff; the PostToolUse hook runs it on edited files.
- Pydantic v2 models with `ConfigDict(extra="forbid")` for every external contract.
- Load YAML with `yaml.safe_load` only. Never `eval`, `exec` or `pickle` untrusted input.
- Async code uses `asyncio`; blocking callables run in a worker thread (`asyncio.to_thread`).
- Heavy imports (numpy, duckdb, httpx, provider SDKs) stay inside functions so `import evalgate` stays < 300 ms.
- Errors that reach the CLI subclass `evalgate.errors.EvalgateError` and carry an exit code.
