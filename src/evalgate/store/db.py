"""DuckDB connections and ordered SQL migrations tracked in ``schema_version``."""

from __future__ import annotations

import re
import time
from importlib import resources
from pathlib import Path
from typing import Any

import duckdb

_MIGRATION = re.compile(r"^(\d{3})_[a-z0-9_]+\.sql$")


def connect(path: Path, read_only: bool = False, lock_timeout_s: float = 5.0) -> duckdb.DuckDBPyConnection:
    """Open a DuckDB file, retrying while another process holds the lock (up to ``lock_timeout_s``)."""
    if not read_only:
        path.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + lock_timeout_s
    while True:
        try:
            return duckdb.connect(str(path), read_only=read_only)
        except duckdb.IOException:
            if time.monotonic() >= deadline:
                raise
            time.sleep(0.1)


def migrations(package: str = "evalgate.store") -> list[tuple[int, str, str]]:
    root = resources.files(package).joinpath("migrations")
    found = []
    for entry in root.iterdir():
        match = _MIGRATION.match(entry.name)
        if match:
            found.append((int(match.group(1)), entry.name, entry.read_text(encoding="utf-8")))
    return sorted(found)


def migrate(con: duckdb.DuckDBPyConnection, package: str = "evalgate.store") -> list[int]:
    """Apply pending migrations in order, each inside one transaction. Returns applied versions."""
    con.execute(
        "CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY, applied_at TIMESTAMP NOT NULL)"
    )
    done = {row[0] for row in con.execute("SELECT version FROM schema_version").fetchall()}
    applied = []
    for version, _name, sql in migrations(package):
        if version in done:
            continue
        con.execute("BEGIN TRANSACTION")
        try:
            con.execute(sql)
            con.execute("INSERT INTO schema_version VALUES (?, now())", [version])
            con.execute("COMMIT")
        except Exception:
            con.execute("ROLLBACK")
            raise
        applied.append(version)
    return applied


def rows(con: duckdb.DuckDBPyConnection, sql: str, params: list[Any] | None = None) -> list[dict[str, Any]]:
    cur = con.execute(sql, params or [])
    cols = [d[0] for d in cur.description or []]
    return [dict(zip(cols, r, strict=True)) for r in cur.fetchall()]
