import json
from pathlib import Path

import pytest

from evalgate.errors import InvalidInputError
from evalgate.report.build import load_report
from evalgate.suite import limits
from evalgate.suite.loader import load_dataset, load_suite_file


def test_oversize_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    row = {"id": "big", "split": "test", "input": {"text": "x" * (limits.MAX_ROW_BYTES + 10)}}
    path = tmp_path / "d.jsonl"
    path.write_text(json.dumps(row) + "\n")
    with pytest.raises(InvalidInputError, match="over the 1000000-byte limit") as info:
        load_dataset(path)
    assert info.value.location == "line 1"

    suite = tmp_path / "s.yaml"
    suite.write_text("description: " + "y" * (limits.MAX_SUITE_BYTES + 1))
    with pytest.raises(InvalidInputError, match="over the 1000000-byte limit"):
        load_suite_file(suite)

    report = tmp_path / "r.json"
    report.write_text("{}")
    monkeypatch.setattr("evalgate.report.build.MAX_REPORT_BYTES", 1)
    with pytest.raises(InvalidInputError, match="report is 2 bytes"):
        load_report(report)


def test_case_count_limit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(limits, "MAX_CASES", 2)
    path = tmp_path / "d.jsonl"
    path.write_text("".join(json.dumps({"id": f"r{i}", "split": "test", "input": {}}) + "\n" for i in range(3)))
    with pytest.raises(InvalidInputError, match="3 cases, over the 2-case limit"):
        load_dataset(path)
