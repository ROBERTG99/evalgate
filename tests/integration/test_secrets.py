"""Secrets come only from the environment and never reach reports or logs."""

import json
import logging
from pathlib import Path

import pytest

from evalgate.report.markdown import render_markdown
from evalgate.runner import RunOptions, run_suite
from evalgate.suite import load_suite
from tests.factories import rows, write_dataset, write_suite

SECRET = "sk-ant-test-0123456789abcdef-NOT-A-REAL-KEY"


def test_secrets_never_in_reports_or_logs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    for var in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "LANGFUSE_SECRET_KEY", "EVALGATE_SERVE_TOKEN"):
        monkeypatch.setenv(var, SECRET)
    data = write_dataset(tmp_path / "d.jsonl", rows(3))
    rubric_metric = {
        "name": "j",
        "kind": "judge",
        "params": {
            "rubric": "evals/rubrics/answer_correctness.v1.yaml",
            "candidate": "output.text",
            "reference": "input.text",
        },
    }
    suite = write_suite(tmp_path / "s.yaml", data, metrics=[rubric_metric])
    caplog.set_level(logging.DEBUG)
    report = run_suite(load_suite(suite), RunOptions(home=tmp_path / "home", resamples=100)).report
    dumped = report.model_dump_json()
    assert SECRET not in dumped
    assert SECRET not in render_markdown(report)
    assert SECRET not in caplog.text
    for db in (tmp_path / "home").glob("*.duckdb"):
        assert SECRET.encode() not in db.read_bytes()
    assert SECRET not in json.dumps(report.extensions)
