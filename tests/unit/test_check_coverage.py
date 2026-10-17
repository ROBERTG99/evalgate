import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def coverage(tmp_path: Path, core: tuple[int, int], overall: float) -> Path:
    data = {
        "totals": {"percent_covered": overall},
        "files": {
            "src/evalgate/stats/gate.py": {"summary": {"covered_lines": core[0], "num_statements": core[1]}},
            "src/evalgate/cli.py": {"summary": {"covered_lines": 1, "num_statements": 10}},
        },
    }
    path = tmp_path / "coverage.json"
    path.write_text(json.dumps(data))
    return path


def run(path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts/check_coverage.py"), str(path)], capture_output=True, text=True
    )


def test_core_package_below_85_fails(tmp_path: Path) -> None:
    out = run(coverage(tmp_path, (84, 100), 90.0))
    assert out.returncode == 1
    assert "stats" in out.stdout and "MISS" in out.stdout


def test_overall_below_70_fails(tmp_path: Path) -> None:
    assert run(coverage(tmp_path, (95, 100), 69.9)).returncode == 1
