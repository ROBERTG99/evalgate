import json
from pathlib import Path

import pytest

from evalgate.errors import InvalidInputError
from evalgate.report import build
from evalgate.report.build import git_sha, load_report, write_report
from evalgate.report.render import fmt_pp, render_check_text
from evalgate.stats.gate import check
from tests.factories import make_report


def test_check_text_names_regression_and_threshold_failures() -> None:
    base = make_report({"acc": [1.0] * 150}, threshold=0.95)
    cand = make_report({"acc": [0.0] * 10 + [1.0] * 140}, threshold=0.95)
    result = check(cand, report_sha256="x", baseline=base, resamples=1000)
    text = render_check_text(result, cand)
    assert text.startswith("evalgate check: FAIL")
    assert "delta acc: 1.0000 -> 0.9333 = -6.67 pp" in text
    assert "FAILED regression: acc -6.67 pp [95% CI" in text
    assert "FAILED threshold: acc value 0.9333" in text


def test_check_text_pass_without_baseline() -> None:
    report = make_report({"acc": [1.0] * 20}, threshold=0.5)
    text = render_check_text(check(report, report_sha256="x", resamples=100), report)
    assert text.startswith("evalgate check: PASS")
    assert "delta" not in text and "FAILED" not in text
    assert fmt_pp(None) == "n/a"


def test_load_report_round_trip_and_errors(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    report = make_report({"acc": [1.0, 0.0]})
    path = write_report(report, tmp_path / "nested" / "r.json")
    assert load_report(path) == report
    with pytest.raises(InvalidInputError, match="report not found"):
        load_report(tmp_path / "missing.json")
    bad = tmp_path / "bad.json"
    bad.write_text("{not json")
    with pytest.raises(InvalidInputError, match="invalid JSON"):
        load_report(bad)
    wrong = tmp_path / "wrong.json"
    wrong.write_text(json.dumps({"schema": "evalgate.report.v1"}))
    with pytest.raises(InvalidInputError):
        load_report(wrong)
    monkeypatch.setattr(build, "MAX_REPORT_BYTES", 10)
    with pytest.raises(InvalidInputError):
        load_report(path)


def test_git_sha_sources(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_SHA", "abc123")
    assert git_sha() == "abc123"
    monkeypatch.delenv("GITHUB_SHA")
    monkeypatch.setattr(build.shutil, "which", lambda _: None)
    assert git_sha() is None


def test_check_text_says_above_for_lower_is_better_metrics() -> None:
    report = make_report({"latency": [0.9] * 20}, threshold=0.5, direction="lower")
    report.metrics["latency"].passed = False  # the factory leaves summaries passing; the runner computes this
    text = render_check_text(check(report, report_sha256="x", resamples=100), report)
    assert "metric latency: 0.9000 threshold 0.5 (above)" in text
