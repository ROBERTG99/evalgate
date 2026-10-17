"""Exit codes: 0 success, 1 gate failed, 2 invalid input, 3 budget abort, 4 internal error, 5 strict export."""

import json
import os
import subprocess
import sys
from pathlib import Path

from tests.factories import make_report, rows, write_dataset, write_suite

ROOT = Path(__file__).resolve().parents[3]
EVALGATE = str(Path(sys.executable).parent / "evalgate")


def cli(*args: str, env: dict[str, str] | None = None, tmp: Path | None = None) -> subprocess.CompletedProcess[str]:
    base = {k: v for k, v in os.environ.items() if not k.startswith(("EVALGATE_", "ANTHROPIC", "OPENAI", "LANGFUSE"))}
    if tmp is not None:
        base["EVALGATE_HOME"] = str(tmp / "home")
    return subprocess.run(
        [EVALGATE, *args], cwd=ROOT, capture_output=True, text=True, env={**base, **(env or {})}, check=False
    )


def judged_suite(tmp_path: Path) -> Path:
    data = write_dataset(
        tmp_path / "d.jsonl",
        [
            {
                "id": f"c{i}",
                "split": "test",
                "input": {"question": "q", "answer": "Within 30 days."},
                "expected": {"answer": "Within 30 days."},
            }
            for i in range(200)
        ],
    )
    metrics = [
        {
            "name": "correct",
            "kind": "judge",
            "threshold": 0.8,
            "params": {"rubric": "evals/rubrics/answer_correctness.v1.yaml"},
        }
    ]
    return write_suite(
        tmp_path / "s.yaml", data, metrics=metrics, target={"python": "tests.fixtures.targets:echo_answer"}
    )


def test_exit_0_run_and_check(tmp_path: Path) -> None:
    data = write_dataset(tmp_path / "d.jsonl", rows(5))
    suite = write_suite(
        tmp_path / "s.yaml",
        data,
        target={"python": "tests.fixtures.targets:echo"},
        metrics=[{"name": "acc", "kind": "regex", "params": {"actual": "output.text", "pattern": "^t"}}],
    )
    out = tmp_path / "r.json"
    assert cli("run", str(suite), "--split", "test", "--out", str(out), tmp=tmp_path).returncode == 0
    res = cli("check", str(out), "--out-json", str(tmp_path / "c.json"), tmp=tmp_path)
    assert res.returncode == 0, res.stdout + res.stderr
    assert json.loads((tmp_path / "c.json").read_text())["passed"] is True


def test_exit_1_gate_failed(tmp_path: Path) -> None:
    rep = make_report({"acc": [1.0] * 100}, extensions={"budget": {"max_p95_ms": 500}}, p95=640.0)
    path = tmp_path / "r.json"
    path.write_text(rep.model_dump_json(by_alias=True))
    res = cli("check", str(path), "--format", "json", tmp=tmp_path)
    assert res.returncode == 1
    assert json.loads(res.stdout)["failures"][0]["reason"] == "budget_p95"
    gh = cli("check", str(path), "--format", "github", tmp=tmp_path)
    assert gh.returncode == 1
    assert "::error title=evalgate budget_p95::" in gh.stdout


def test_exit_2_invalid_input(tmp_path: Path) -> None:
    assert cli("run", str(tmp_path / "missing.yaml"), "--out", str(tmp_path / "r.json"), tmp=tmp_path).returncode == 2
    bad = tmp_path / "bad.json"
    bad.write_text('{"schema": "evalgate.report.v1"}')
    res = cli("check", str(bad), tmp=tmp_path)
    assert res.returncode == 2
    assert "missing required key" in res.stderr
    assert cli("schema", "nope", tmp=tmp_path).returncode == 2
    assert cli("check", str(bad), "--format", "xml", tmp=tmp_path).returncode == 2


def test_exit_3_budget_abort_before_provider_call(tmp_path: Path) -> None:
    suite = judged_suite(tmp_path)
    res = cli(
        "run",
        str(suite),
        "--split",
        "test",
        "--out",
        str(tmp_path / "r.json"),
        tmp=tmp_path,
        env={
            "EVALGATE_LLM_PROVIDER": "anthropic",
            "LIVE_EVAL_BUDGET_USD": "0.0001",
            "EVALGATE_JUDGE_MODEL": "claude-opus-5-5",
        },
    )
    assert res.returncode == 3, res.stderr
    assert "live estimate" in res.stderr  # the estimate is printed first
    assert "no provider call was made" in res.stderr
    assert not (tmp_path / "r.json").exists()


def test_exit_4_internal_error(tmp_path: Path) -> None:
    data = write_dataset(tmp_path / "d.jsonl", rows(2))
    suite = write_suite(tmp_path / "s.yaml", data)
    out_dir = tmp_path / "is_a_directory"
    out_dir.mkdir()
    res = cli("run", str(suite), "--split", "test", "--out", str(out_dir), tmp=tmp_path)
    assert res.returncode == 4
    assert "internal error" in res.stderr


def test_exit_5_strict_export(tmp_path: Path) -> None:
    rep = make_report({"acc": [1.0] * 3})
    path = tmp_path / "r.json"
    path.write_text(rep.model_dump_json(by_alias=True))
    res = cli("export", "langfuse", str(path), "--strict", "--host", "http://127.0.0.1:9", tmp=tmp_path)
    assert res.returncode == 5, res.stderr
    lenient = cli("export", "langfuse", str(path), "--host", "http://127.0.0.1:9", tmp=tmp_path)
    assert lenient.returncode == 0
    assert "warning" in lenient.stderr


def test_help_lists_every_command() -> None:
    out = cli("--help").stdout
    for command in ["run", "check", "report", "calibrate", "serve", "import", "export", "gc", "schema"]:
        assert f"  {command} " in out, command
    assert "promptfoo" in cli("import", "--help").stdout
    assert "langfuse" in cli("export", "--help").stdout
    assert cli("--version").stdout.strip() == "evalgate 0.1.0"


def test_report_command_writes_md_and_html(tmp_path: Path) -> None:
    rep = make_report({"acc": [1.0, 0.0]}, threshold=0.4)
    path = tmp_path / "r.json"
    path.write_text(rep.model_dump_json(by_alias=True))
    res = cli(
        "report",
        str(path),
        "--md",
        str(tmp_path / "r.md"),
        "--html",
        str(tmp_path / "r.html"),
        "--baseline",
        str(path),
        tmp=tmp_path,
    )
    assert res.returncode == 0, res.stderr
    assert (tmp_path / "r.md").read_text().startswith("<!-- evalgate:report -->")
    assert "<html" in (tmp_path / "r.html").read_text()


def test_gc_and_audit_verification(tmp_path: Path) -> None:
    rep = make_report({"acc": [1.0] * 3})
    path = tmp_path / "r.json"
    path.write_text(rep.model_dump_json(by_alias=True))
    assert cli("check", str(path), tmp=tmp_path).returncode == 0
    res = cli("gc", "--verify-audit", tmp=tmp_path)
    assert res.returncode == 0, res.stderr
    assert "chain verified" in res.stderr
