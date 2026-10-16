from datetime import UTC, datetime, timedelta
from pathlib import Path

from evalgate.contracts import MetricScore, StepRecord
from evalgate.report.build import CaseOutcome
from evalgate.store import RunStore
from evalgate.store.db import connect, migrate, migrations
from tests.factories import make_report


def outcome(case_id: str) -> CaseOutcome:
    return CaseOutcome(
        case_id=case_id,
        split="test",
        passed=True,
        cost_usd=0.01,
        latency_ms=12.5,
        attempts=2,
        scores=[MetricScore(name="acc", value=1.0, passed=True, details={"x": 1})],
        steps=[StepRecord(step=0, node="classify", kind="llm", model="toy-model", input_tokens=10, output_tokens=2)],
    )


def test_migrate_idempotent(tmp_path: Path) -> None:
    con = connect(tmp_path / "runs.duckdb")
    first = migrate(con)
    second = migrate(con)
    assert first == [v for v, _, _ in migrations()]
    assert second == []
    versions = con.execute("SELECT version FROM schema_version ORDER BY version").fetchall()
    assert [v[0] for v in versions] == first
    tables = {r[0] for r in con.execute("SELECT table_name FROM information_schema.tables").fetchall()}
    assert {"runs", "case_results", "metric_scores", "steps", "gate_audit", "schema_version"} <= tables
    con.close()


def test_insert_and_resume_roundtrip(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs.duckdb")
    store.insert_case("run-1", outcome("a"))
    store.insert_case("run-1", outcome("a"))  # idempotent on (run_id, case_id)
    store.insert_case("run-1", outcome("b"))
    cases = store.get_cases("run-1")
    assert [c.case_id for c in cases] == ["a", "b"]
    assert cases[0].scores[0].details == {"x": 1}
    assert cases[0].steps[0].model == "toy-model"
    assert cases[0].attempts == 2
    report = make_report({"acc": [1.0, 0.0]})
    store.finish_run(report)
    store.set_report_path(report.run_id, "r.json", "abc")
    runs = store.runs()
    assert runs[0]["report_path"] == "r.json"
    store.close()


def test_check_constraints(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs.duckdb")
    bad = outcome("c")
    bad.split = "train"
    try:
        store.insert_case("run-2", bad)
        raised = False
    except Exception:
        raised = True
    assert raised
    store.close()


def test_audit_chain_detects_tamper(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs.duckdb")
    for i in range(3):
        store.audit_append(
            report_sha256=f"r{i}",
            baseline_sha256=None,
            git_sha="g",
            decision="pass" if i else "fail",
            failures=[{"metric": "acc", "reason": "threshold"}] if not i else [],
            actor="ci",
        )
    assert store.verify_audit() == (True, None)
    store.con.execute("UPDATE gate_audit SET decision = 'pass' WHERE seq = 1")
    assert store.verify_audit() == (False, 1)
    store.close()


def test_gc_prunes_old_runs_and_audit(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs.duckdb")
    old = make_report({"acc": [1.0]})
    store.finish_run(old)
    store.insert_case(old.run_id, outcome("a"))
    now = datetime(2026, 10, 16, tzinfo=UTC) + timedelta(days=40)
    store.audit_append(
        report_sha256="x",
        baseline_sha256=None,
        git_sha=None,
        decision="pass",
        failures=[],
        actor=None,
        ts=now - timedelta(days=400),
    )
    store.audit_append(
        report_sha256="y",
        baseline_sha256=None,
        git_sha=None,
        decision="pass",
        failures=[],
        actor=None,
        ts=now - timedelta(days=1),
    )
    pruned = store.gc(keep_days=30, now=now)
    assert pruned == {"runs": 1, "audit": 1}
    assert store.get_cases(old.run_id) == []
    assert store.verify_audit() == (True, None)
    store.close()
