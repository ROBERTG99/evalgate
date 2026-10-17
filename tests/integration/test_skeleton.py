import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_trivial_suite_writes_report(tmp_path: Path) -> None:
    out = tmp_path / "r.json"
    proc = subprocess.run(
        [
            str(Path(sys.executable).parent / "evalgate"),  # the installed entry point, not `python -m`
            "run",
            "tests/fixtures/suites/trivial.yaml",
            "--split",
            "dev",
            "--out",
            str(out),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        env={"EVALGATE_HOME": str(tmp_path / "home"), "PATH": "/usr/bin"},
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    report = json.loads(out.read_text())
    assert report["schema"] == "evalgate.report.v1"
    assert report["n_cases"] == 2
    assert report["metrics"]["label_accuracy"]["value"] == 1.0
