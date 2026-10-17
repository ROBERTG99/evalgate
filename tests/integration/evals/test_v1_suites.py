from pathlib import Path

import pytest

from evalgate.report.build import load_report
from evalgate.runner import RunOptions, run_suite
from evalgate.stats.gate import check
from evalgate.suite import load_suite

ROOT = Path(__file__).resolve().parents[3]
SUITES = ["classify", "extract", "answer"]


def run(suite: str, version: str, tmp_path: Path, toys_url: str, monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    monkeypatch.setenv("EVALGATE_TOYS_URL", toys_url)
    monkeypatch.setenv("EVALGATE_TOY_VERSION", version)
    loaded = load_suite(ROOT / f"evals/suites/{suite}.yaml", split="test")
    return run_suite(
        loaded, RunOptions(split="test", home=tmp_path / version, use_store=False, cache_mode="off")
    ).report


@pytest.mark.parametrize("suite", SUITES)
def test_v1_passes_v2_fails(suite: str, tmp_path: Path, toys_url: str, monkeypatch: pytest.MonkeyPatch) -> None:
    baseline = load_report(ROOT / f"evals/baselines/{suite}.json")
    v1 = run(suite, "v1", tmp_path, toys_url, monkeypatch)
    v2 = run(suite, "v2", tmp_path, toys_url, monkeypatch)
    r1 = check(v1, report_sha256="v1", baseline=baseline)
    r2 = check(v2, report_sha256="v2", baseline=baseline)
    assert r1.passed, r1.failures
    assert not r2.passed
    assert any(f.reason == "regression" for f in r2.failures)
    for name, m in v1.metrics.items():  # quality metrics identical to the baseline: the toys are deterministic
        assert m.value == baseline.metrics[name].value, name


def test_section_11_thresholds_on_baselines() -> None:
    reports = {s: load_report(ROOT / f"evals/baselines/{s}.json") for s in SUITES}
    assert reports["classify"].metrics["label_accuracy"].value >= 0.90
    assert reports["extract"].metrics["schema_valid"].value == 1.0
    assert reports["extract"].metrics["total_tolerance"].value >= 0.95
    assert reports["answer"].metrics["answer_contains"].value >= 0.85
    assert reports["answer"].metrics["tool_calls"].value >= 0.95
    assert reports["answer"].metrics["answer_correctness"].value >= 0.85
