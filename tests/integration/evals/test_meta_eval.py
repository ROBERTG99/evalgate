import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]


@pytest.mark.slow
def test_report_fields(tmp_path: Path) -> None:
    out = tmp_path / "meta-eval.json"
    proc = subprocess.run(
        [sys.executable, "scripts/meta_eval.py", "--out", str(out), "--resamples", "2000"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=600,
    )
    assert out.exists(), proc.stderr
    data = json.loads(out.read_text())
    assert data["schema"] == "evalgate.meta_eval.v1"
    assert data["regressions"] == 30 and data["neutral"] == 20
    assert 0.0 <= data["detection_rate"] <= 1.0 and 0.0 <= data["false_positive_rate"] <= 1.0
    assert data["thresholds"] == {"detection_min": 0.9, "false_positive_max": 0.1}
    assert set(data["by"]) == {"split", "system", "kind"}
    assert len(data["variants"]) == 50
    assert {"id", "system", "mutation", "regression", "detected", "failures"} <= set(data["variants"][0])
    assert proc.returncode == (0 if data["passed"] else 1)
    assert data["passed"], proc.stdout[-2000:]
