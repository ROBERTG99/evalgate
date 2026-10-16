# ADR-0001: DuckDB for the run store and the response cache

- Status: Accepted
- Date: 2026-10-16

## Context

evalgate keeps two kinds of local state. The run store records every run, its cases, metric scores, priced steps and an append-only audit trail of gate decisions. The response cache stores judge responses (and, with `--cache-targets`, target responses) so that an unchanged re-run makes no provider calls (FR-10). Both must work offline, inside a CI job and on a laptop, with no service to start, and the library installs with `pip install evalgate`.

The data is analytical: the viewer, the comparator and ad hoc questions ("p95 latency per suite over the last month", "which cases regressed") read many rows of a few columns. Reports are the contract (`evalgate.report.v1`); the database is a local index next to them, kept as a 14-day CI artifact (build spec §4.3).

## Decision

Use DuckDB files under `EVALGATE_HOME` (default `.evalgate/`): `runs.duckdb` for the run store ([src/evalgate/store/](../../src/evalgate/store/)) and `cache.duckdb` for the response cache ([src/evalgate/cache/](../../src/evalgate/cache/)).

- Schema changes are numbered SQL files applied in order, each in one transaction, and tracked in `schema_version` ([src/evalgate/store/db.py](../../src/evalgate/store/db.py)): [001_init.sql](../../src/evalgate/store/migrations/001_init.sql) and [002_audit_anchor.sql](../../src/evalgate/store/migrations/002_audit_anchor.sql) for the run store, [cache migrations](../../src/evalgate/cache/migrations/001_init.sql) for the cache.
- Enumerations are enforced by `CHECK` constraints (`split`, `mode`, step `kind` and `status`, audit `decision`).
- `gate_audit` is append-only and hash-chained: each row stores `prev_hash` and `hash = sha256(prev_hash + canonical_json(record))` ([src/evalgate/store/runstore.py](../../src/evalgate/store/runstore.py)). `evalgate gc --verify-audit` recomputes the chain. When retention prunes the oldest rows, the last pruned `seq` and `hash` go into `audit_anchor`, so verification can tell retention from tampering.
- Cache rows are keyed by the cassette key and inserted with `ON CONFLICT DO NOTHING`. If another process holds the cache file for more than 5 seconds, the cache falls back to read-only, and to off when even a read-only connection fails (`LOCK_TIMEOUT_S` in [`src/evalgate/cache/__init__.py`](../../src/evalgate/cache/__init__.py)).
- `duckdb` is imported inside functions so that `import evalgate` stays light.

## Alternatives considered

- **SQLite (rejected).** It ships with Python, so it would cost no dependency, and it handles concurrent readers well. It was rejected because the workload is analytical (aggregates and percentiles over runs, cases and steps) and because DuckDB offers a native `JSON` column type and columnar scans for that workload in the same single-file, serverless model. The difference in query speed was not measured for this project; the choice rests on the feature fit, not on a benchmark.
- **Postgres (rejected).** It would give multi-writer concurrency and a central audit store, but it needs a running server. That breaks the offline-first constraint, adds a service container to every CI job that uses the action, and makes `pip install evalgate` insufficient on its own.

## Consequences

### Positive

- One file per store, no server, works the same in CI and locally; the `evals` workflow uploads `.evalgate/*.duckdb` as 14-day artifacts ([.github/workflows/evals.yml](../../.github/workflows/evals.yml)).
- The audit chain makes deletion or edits of gate decisions detectable (`evalgate gc --verify-audit`), including head pruning outside `evalgate gc` (see the `audit_anchor` entry in [docs/DECISIONS.md](../DECISIONS.md)).
- Migrations are plain SQL and reviewable; the `add-migration` skill documents the procedure.
- An unchanged cached re-run of 200 judged cases took 1.3421 s against a 10 s budget (NFR-3, `evals/reports/bench.json`, `make bench`).

### Negative

- `duckdb` is a large binary dependency. The `python:3.13-slim` runtime image measured 260 MB with numpy and duckdb, over the 250 MB budget, which is why the image moved to distroless (202 MB) ([docs/DECISIONS.md](../DECISIONS.md)).
- DuckDB allows one read-write process per file. Parallel jobs on one machine wait up to 5 seconds for the lock and then degrade (cache read-only or off; run store skipped with a warning while the report is still written).
- The audit trail is only as wide as one machine's `runs.duckdb`; there is no central audit store ([docs/KNOWN_LIMITATIONS.md](../KNOWN_LIMITATIONS.md)).
- DuckDB file format upgrades follow DuckDB releases; the version is pinned in `uv.lock`, and the files are treated as rebuildable caches, not as the record of truth (the reports are).
