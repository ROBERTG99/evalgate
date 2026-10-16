---
name: add-migration
description: Add a DuckDB schema migration to the evalgate run store or cache. Use when a table, column, index or constraint in runs.duckdb or cache.duckdb must change.
---

# Add a DuckDB migration

Migrations are plain SQL files `src/evalgate/store/migrations/NNN_<name>.sql`, applied in numeric order, each inside one transaction, and tracked in `schema_version(version INTEGER PRIMARY KEY, applied_at TIMESTAMP)`. Applying them twice is a no-op.

## Steps

1. List the existing migrations and pick the next number:

   ```bash
   ls src/evalgate/store/migrations/
   ```

   Use three digits and snake case, for example `004_add_case_tags.sql`. Never edit or renumber a migration that is already committed.
2. Write the failing test first in `tests/integration/store/test_store.py` (or a new file there): migrate a fresh database in `tmp_path`, assert the new column, index or constraint exists, and keep `test_migrate_idempotent` passing.
3. Run it and watch it fail:

   ```bash
   uv run pytest tests/integration/store/test_store.py -x
   ```

4. Write the SQL. Prefer additive changes (`ALTER TABLE ... ADD COLUMN ... DEFAULT ...`, `CREATE INDEX IF NOT EXISTS`). Keep the CHECK constraints on `split`, `mode`, `kind` and `status`. Never change `gate_audit` in a way that breaks the hash chain; it stays append-only.
5. Update the Python side: queries and dataclasses in `src/evalgate/store/` (and `src/evalgate/cache/` for `cache.duckdb`), always with parameterised queries. If the change is visible in a contract, update `src/evalgate/contracts/` and regenerate `schemas/` with `uv run python scripts/export_schemas.py` (`make schemas` then checks for drift).
6. Add an upgrade test: create a database at the previous version with sample rows, migrate, and assert the rows survive and `evalgate gc --verify-audit` still passes.
7. Run `uv run pytest tests/integration/store tests/integration/cache -q`, then `make check-fast`.
8. Record evidence in `PROGRESS.md`; if the change is architectural, add a note to `docs/DECISIONS.md` or use the `new-adr` skill.
