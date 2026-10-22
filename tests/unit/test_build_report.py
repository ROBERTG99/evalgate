import json
import re
import shutil
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import build_eval_report  # noqa: E402

FIXTURES = ROOT / "tests/fixtures/eval_reports"


def numeric_leaves(value: Any) -> list[float]:
    if isinstance(value, bool):
        return []
    if isinstance(value, int | float):
        return [float(value)]
    if isinstance(value, dict):
        return [x for v in value.values() for x in numeric_leaves(v)]
    if isinstance(value, list):
        return [x for v in value for x in numeric_leaves(v)]
    return []


def renderings(x: float) -> set[str]:
    forms = {f"{x:.0f}", f"{x:.2f}", f"{x:.3f}", f"{x:.4f}", f"{x:+.2f}", f"{x:+.3f}", f"{x * 100:+.2f}", f"{x:,.0f}"}
    return {f.lstrip("+") for f in forms} | forms


def test_numbers_come_from_reports(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    shutil.copytree(FIXTURES, reports)
    out = tmp_path / "REPORT.md"
    text, _passed, missing = build_eval_report.build(reports, out)
    assert missing == []
    allowed: set[str] = set()
    for path in reports.glob("*.json"):
        for x in numeric_leaves(json.loads(path.read_text())):
            allowed |= renderings(x)
    allowed |= {
        "0.92",
        "0.98",
        "0.90",
        "0.10",
        "0.80",
        "0.70",
        "0.05",
        "0.00",
        "0.85",
        "0.95",
        "1.00",
        "1.0",
        "11",
        "1.0.0",
        "1337",
        "95",
        "256",
    }  # threshold count, generator version, seed, "95% CI", "sha256"
    body = re.sub(r"\(reports/[^)]*\)|`[^`]*`", "", text)  # file links and code spans (ids, hashes, names)
    numbers = re.findall(r"[+-]?\d+(?:,\d{3})*(?:\.\d+)?", body)
    unexplained = sorted({n for n in numbers if n not in allowed and n.lstrip("+-") not in allowed})
    assert unexplained == []
    # change a number in a report and it changes in REPORT.md
    data = json.loads((reports / "classify.json").read_text())
    data["metrics"]["label_accuracy"]["value"] = 0.9123
    (reports / "classify.json").write_text(json.dumps(data))
    assert "0.9123" in build_eval_report.build(reports, out)[0]


def test_missing_reports_fail_check(tmp_path: Path) -> None:
    text, passed, missing = build_eval_report.build(tmp_path, tmp_path / "REPORT.md")
    assert not passed
    assert "meta-eval.json" in missing
    assert "Live evals were not run" in text
