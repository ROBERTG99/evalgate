"""The run store (``runs.duckdb``): runs, cases, scores, steps and the hash-chained gate audit."""

from __future__ import annotations

import hashlib
import json
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from evalgate.contracts import MetricScore, Report, StepRecord
from evalgate.ids import canonical_json
from evalgate.report.build import CaseOutcome
from evalgate.store.db import connect, migrate, rows

GENESIS = "0" * 64


def _ts(value: str | None) -> datetime:
    if not value:
        return datetime.now(UTC).replace(tzinfo=None)
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC).replace(tzinfo=None)


def audit_hash(prev_hash: str, record: dict[str, Any]) -> str:
    return hashlib.sha256((prev_hash + canonical_json(record)).encode("utf-8")).hexdigest()


class RunStore:
    def __init__(self, path: Path, read_only: bool = False) -> None:
        self.path = path
        self.con = connect(path, read_only=read_only)
        self._lock = threading.Lock()
        if not read_only:
            migrate(self.con)

    def close(self) -> None:
        self.con.close()

    # writes ----------------------------------------------------------------------------------
    def insert_case(self, run_id: str, o: CaseOutcome) -> None:
        with self._lock:
            self.con.execute("BEGIN TRANSACTION")
            try:
                self.con.execute(
                    "INSERT INTO case_results VALUES (?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT DO NOTHING",
                    [run_id, o.case_id, o.split, o.passed, o.cost_usd, o.latency_ms, o.attempts, o.error],
                )
                for s in o.scores:
                    self.con.execute(
                        "INSERT INTO metric_scores VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT DO NOTHING",
                        [run_id, o.case_id, s.name, s.value, s.passed, json.dumps(s.details, default=str)],
                    )
                for st in o.steps:
                    if not isinstance(st, StepRecord):
                        continue
                    self.con.execute(
                        "INSERT INTO steps VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT DO NOTHING",
                        [
                            run_id,
                            o.case_id,
                            st.step,
                            st.task_id or o.case_id,
                            st.node,
                            st.kind,
                            st.model,
                            st.prompt_version,
                            st.input_tokens,
                            st.output_tokens,
                            st.cost_usd,
                            st.latency_ms,
                            st.status,
                            st.error,
                            st.started_at.astimezone(UTC).replace(tzinfo=None) if st.started_at else None,
                        ],
                    )
                self.con.execute("COMMIT")
            except Exception:
                self.con.execute("ROLLBACK")
                raise

    def finish_run(self, report: Report, report_path: str | None = None, report_sha256: str | None = None) -> None:
        split = (report.extensions or {}).get("split")
        passed = all(m.passed for m in report.metrics.values())
        with self._lock:
            self.con.execute(
                "INSERT OR REPLACE INTO runs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    report.run_id,
                    report.suite,
                    split if split in ("dev", "test") else None,
                    _ts(report.created_at),
                    report.git_sha,
                    report.mode,
                    report.n_cases,
                    passed,
                    report.cost_usd_total,
                    report.latency_p50_ms,
                    report.latency_p95_ms,
                    report_path,
                    report_sha256,
                ],
            )

    def set_report_path(self, run_id: str, report_path: str, report_sha256: str) -> None:
        with self._lock:
            self.con.execute(
                "UPDATE runs SET report_path = ?, report_sha256 = ? WHERE run_id = ?",
                [report_path, report_sha256, run_id],
            )

    # reads -----------------------------------------------------------------------------------
    def runs(self, suite: str | None = None) -> list[dict[str, Any]]:
        if suite:
            return rows(self.con, "SELECT * FROM runs WHERE suite = ? ORDER BY created_at DESC", [suite])
        return rows(self.con, "SELECT * FROM runs ORDER BY created_at DESC")

    def get_cases(self, run_id: str) -> list[CaseOutcome]:
        cases = rows(self.con, "SELECT * FROM case_results WHERE run_id = ? ORDER BY case_id", [run_id])
        scores = rows(self.con, "SELECT * FROM metric_scores WHERE run_id = ?", [run_id])
        steps = rows(self.con, "SELECT * FROM steps WHERE run_id = ? ORDER BY case_id, step", [run_id])
        by_case: dict[str, list[MetricScore]] = {}
        for s in scores:
            details = json.loads(s["details"]) if s["details"] else {}
            by_case.setdefault(s["case_id"], []).append(
                MetricScore(name=s["metric"], value=s["value"], passed=s["passed"], details=details)
            )
        steps_by_case: dict[str, list[StepRecord]] = {}
        for st in steps:
            steps_by_case.setdefault(st["case_id"], []).append(
                StepRecord(
                    run_id=run_id,
                    task_id=st["task_id"] or st["case_id"],
                    step=st["step"],
                    node=st["node"],
                    kind=st["kind"],
                    model=st["model"],
                    prompt_version=st["prompt_version"],
                    input_tokens=st["input_tokens"],
                    output_tokens=st["output_tokens"],
                    cost_usd=st["cost_usd"],
                    latency_ms=st["latency_ms"],
                    status=st["status"],
                    error=st["error"],
                    started_at=st["started_at"].replace(tzinfo=UTC) if st["started_at"] else None,
                )
            )
        return [
            CaseOutcome(
                case_id=c["case_id"],
                split=c["split"],
                scores=by_case.get(c["case_id"], []),
                passed=c["passed"],
                cost_usd=c["cost_usd"],
                latency_ms=c["latency_ms"],
                attempts=c["attempts"],
                error=c["error"],
                steps=steps_by_case.get(c["case_id"], []),
            )
            for c in cases
        ]

    # audit -----------------------------------------------------------------------------------
    def audit_append(
        self,
        *,
        report_sha256: str,
        baseline_sha256: str | None,
        git_sha: str | None,
        decision: str,
        failures: list[dict[str, Any]],
        actor: str | None,
        ts: datetime | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            last = self.con.execute("SELECT seq, hash FROM gate_audit ORDER BY seq DESC LIMIT 1").fetchone()
            seq = (last[0] + 1) if last else 1
            prev = last[1] if last else GENESIS
            stamp = (ts or datetime.now(UTC)).astimezone(UTC).replace(tzinfo=None, microsecond=0)
            record = {
                "seq": seq,
                "ts": stamp.isoformat(),
                "report_sha256": report_sha256,
                "baseline_sha256": baseline_sha256,
                "git_sha": git_sha,
                "decision": decision,
                "failures": failures,
                "actor": actor,
            }
            digest = audit_hash(prev, record)
            self.con.execute(
                "INSERT INTO gate_audit VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    seq,
                    stamp,
                    report_sha256,
                    baseline_sha256,
                    git_sha,
                    decision,
                    canonical_json(failures),
                    actor,
                    prev,
                    digest,
                ],
            )
            return {**record, "prev_hash": prev, "hash": digest}

    def verify_audit(self) -> tuple[bool, int | None]:
        """Recompute the hash chain. Returns ``(ok, first_bad_seq)``."""
        audit = rows(self.con, "SELECT * FROM gate_audit ORDER BY seq")
        # After retention pruned the head, the chain continues from the oldest kept row's prev_hash.
        prev = GENESIS if not audit or audit[0]["seq"] == 1 else audit[0]["prev_hash"]
        for row in audit:
            record = {
                "seq": row["seq"],
                "ts": row["ts"].isoformat(),
                "report_sha256": row["report_sha256"],
                "baseline_sha256": row["baseline_sha256"],
                "git_sha": row["git_sha"],
                "decision": row["decision"],
                "failures": json.loads(row["failures"]) if row["failures"] else [],
                "actor": row["actor"],
            }
            if row["prev_hash"] != prev or audit_hash(prev, record) != row["hash"]:
                return False, int(row["seq"])
            prev = row["hash"]
        return True, None

    # retention -------------------------------------------------------------------------------
    def gc(self, keep_days: int = 30, audit_keep_days: int = 365, now: datetime | None = None) -> dict[str, int]:
        """Prune runs (and their cases) older than ``keep_days``. ``gate_audit`` is pruned from the head
        only (oldest rows), and the chain stays verifiable because each kept row stores ``prev_hash``."""
        current = (now or datetime.now(UTC)).astimezone(UTC).replace(tzinfo=None)
        run_cut = current - timedelta(days=keep_days)
        audit_cut = current - timedelta(days=audit_keep_days)
        with self._lock:
            old = [r[0] for r in self.con.execute("SELECT run_id FROM runs WHERE created_at < ?", [run_cut]).fetchall()]
            for table in ("steps", "metric_scores", "case_results", "runs"):
                for run_id in old:
                    self.con.execute(f"DELETE FROM {table} WHERE run_id = ?", [run_id])  # noqa: S608 - fixed names
            n_audit = self.con.execute("SELECT count(*) FROM gate_audit WHERE ts < ?", [audit_cut]).fetchone()
            self.con.execute("DELETE FROM gate_audit WHERE ts < ?", [audit_cut])
        return {"runs": len(old), "audit": int(n_audit[0]) if n_audit else 0}
