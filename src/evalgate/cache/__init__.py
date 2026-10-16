"""Response cache (``cache.duckdb``) keyed by cassette key. Modes: rw, ro, off.

If the file stays locked by another process for more than 5 seconds, the cache falls back to
read-only, and to off when even a read-only connection is impossible.
"""

from __future__ import annotations

import json
import logging
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import duckdb

from evalgate.store.db import connect, migrate

log = logging.getLogger("evalgate.cache")
LOCK_TIMEOUT_S = 5.0


class ResponseCache:
    def __init__(self, path: Path, mode: str = "rw", lock_timeout_s: float = LOCK_TIMEOUT_S) -> None:
        self.path = path
        self.requested_mode = mode
        self.mode = mode
        self.con: duckdb.DuckDBPyConnection | None = None
        self.hits = 0
        self.misses = 0
        self.fallback: str | None = None
        self._lock = threading.Lock()
        if mode == "off":
            return
        if mode == "rw":
            try:
                self.con = connect(path, read_only=False, lock_timeout_s=lock_timeout_s)
                try:
                    migrate(self.con, package="evalgate.cache")
                except Exception:
                    self.con.close()
                    self.con = None
                    raise
                return
            except duckdb.IOException as exc:
                self.fallback = f"cache locked for {lock_timeout_s:.0f}s, read-only fallback: {exc}"
                log.warning(self.fallback)
                self.mode = "ro"
        if not path.exists():
            self.mode = "off"
            return
        try:
            self.con = connect(path, read_only=True, lock_timeout_s=0.5)
        except duckdb.IOException as exc:
            self.fallback = f"cache unavailable, running without it: {exc}"
            log.warning(self.fallback)
            self.mode = "off"
            self.con = None

    def close(self) -> None:
        with self._lock:  # never while a worker thread is reading or writing
            if self.con is not None:
                self.con.close()
                self.con = None

    def get(self, key: str, ttl_days: int | None = None) -> dict[str, Any] | None:
        """The row for ``key`` unless it is older than ``ttl_days`` (default EVALGATE_CACHE_TTL_DAYS)."""
        if self.con is None:
            return None
        from evalgate import config

        cut = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=ttl_days or config.cache_ttl_days())
        with self._lock:
            try:
                row = self.con.execute(
                    "SELECT response, input_tokens, output_tokens, cost_usd, latency_ms, model, request_digest "
                    "FROM responses WHERE key = ? AND created_at >= ?",
                    [key, cut],
                ).fetchone()
            except duckdb.CatalogException:  # read-only file without the table yet
                return None
            if row is None:
                self.misses += 1
                return None
            self.hits += 1
            if self.mode == "rw":
                self.con.execute("UPDATE responses SET hits = hits + 1 WHERE key = ?", [key])
        return {
            "response": json.loads(row[0]),
            "input_tokens": row[1],
            "output_tokens": row[2],
            "cost_usd": row[3],
            "latency_ms": row[4],
            "model": row[5],
            "request_digest": row[6],
        }

    def put(
        self,
        key: str,
        *,
        route: str,
        model: str | None,
        prompt_version: str | None,
        request_digest: str | None,
        response: dict[str, Any],
        input_tokens: int = 0,
        output_tokens: int = 0,
        cost_usd: float = 0.0,
        latency_ms: float = 0.0,
        replace: bool = False,
    ) -> None:
        """Insert once (``ON CONFLICT DO NOTHING``); ``replace`` lets a live response supersede a fake one."""
        if self.con is None or self.mode != "rw":
            return
        verb = (
            "INSERT OR REPLACE INTO responses VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)"
            if replace
            else ("INSERT INTO responses VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0) ON CONFLICT DO NOTHING")
        )
        with self._lock:
            self.con.execute(
                verb,
                [
                    key,
                    route,
                    model,
                    prompt_version,
                    request_digest,
                    json.dumps(response, sort_keys=True),
                    input_tokens,
                    output_tokens,
                    cost_usd,
                    latency_ms,
                    datetime.now(UTC).replace(tzinfo=None),
                ],
            )

    def gc(self, ttl_days: int) -> int:
        if self.con is None or self.mode != "rw":
            return 0
        cut = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=ttl_days)
        with self._lock:
            row = self.con.execute("SELECT count(*) FROM responses WHERE created_at < ?", [cut]).fetchone()
            self.con.execute("DELETE FROM responses WHERE created_at < ?", [cut])
        return int(row[0]) if row else 0
