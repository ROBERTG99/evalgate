"""Reports written outside evalgate must not fail the gate open (non-finite scores, duplicate case ids)."""

import json
from pathlib import Path

import pytest

from evalgate.errors import InvalidInputError
from evalgate.report.build import load_report, write_report
from tests.factories import make_report


def test_nan_score_from_a_file_is_rejected(tmp_path: Path) -> None:
    report = make_report({"acc": [0.0] * 150})
    data = report.model_dump(mode="json", by_alias=True)
    data["cases"][0]["scores"]["acc"] = float("nan")
    path = tmp_path / "nan.json"
    path.write_text(json.dumps(data))  # json.dumps writes NaN, json.loads accepts it
    with pytest.raises(InvalidInputError):
        load_report(path)


@pytest.mark.parametrize("field", ["value", "ci_low"])
def test_non_finite_metric_summary_is_rejected(tmp_path: Path, field: str) -> None:
    data = make_report({"acc": [1.0] * 20}).model_dump(mode="json", by_alias=True)
    data["metrics"]["acc"][field] = float("inf")
    path = tmp_path / "inf.json"
    path.write_text(json.dumps(data))
    with pytest.raises(InvalidInputError):
        load_report(path)


def test_duplicate_case_ids_are_rejected(tmp_path: Path) -> None:
    data = make_report({"acc": [1.0] * 20}).model_dump(mode="json", by_alias=True)
    data["cases"][1]["id"] = data["cases"][0]["id"]
    path = tmp_path / "dup.json"
    path.write_text(json.dumps(data))
    with pytest.raises(InvalidInputError, match="duplicate case id"):
        load_report(path)


def test_valid_report_still_round_trips(tmp_path: Path) -> None:
    report = make_report({"acc": [1.0, 0.0] * 10})
    assert load_report(write_report(report, tmp_path / "ok.json")) == report
