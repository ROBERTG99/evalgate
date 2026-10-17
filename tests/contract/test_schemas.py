"""Schema drift and the cross-language report contract."""

import json
import subprocess
import sys
from pathlib import Path

import jsonschema
import pytest

from evalgate.contracts import SCHEMA_MODELS, Report, json_schema

ROOT = Path(__file__).resolve().parents[2]
SCHEMAS = ROOT / "schemas"


def test_no_drift() -> None:
    proc = subprocess.run(
        [sys.executable, "scripts/export_schemas.py", "--check"], cwd=ROOT, capture_output=True, text=True, check=False
    )
    assert proc.returncode == 0, proc.stderr
    for name in SCHEMA_MODELS:
        on_disk = json.loads((SCHEMAS / f"{name}.json").read_text())
        assert on_disk == json_schema(name)


def test_minimal_producer_report_accepted() -> None:
    data = json.loads((ROOT / "tests/contract/fixtures/report_minimal_producer.json").read_text())
    schema = json.loads((SCHEMAS / "evalgate.report.v1.json").read_text())
    jsonschema.validate(data, schema)
    report = Report.model_validate(data)
    assert report.extensions is None
    assert report.metrics["answer_correctness"].passed is False


@pytest.mark.parametrize("name", list(SCHEMA_MODELS))
def test_schemas_are_valid_draft_2020_12(name: str) -> None:
    schema = json.loads((SCHEMAS / f"{name}.json").read_text())
    jsonschema.Draft202012Validator.check_schema(schema)
    assert schema["$id"].endswith(f"{name}.json")


def test_unknown_report_key_rejected() -> None:
    data = json.loads((ROOT / "tests/contract/fixtures/report_minimal_producer.json").read_text())
    data["surprise"] = 1
    schema = json.loads((SCHEMAS / "evalgate.report.v1.json").read_text())
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(data, schema)


def test_cli_schema_command_matches_files() -> None:
    proc = subprocess.run(
        [sys.executable, "-m", "evalgate.cli", "schema", "report"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0
    assert json.loads(proc.stdout) == json.loads((SCHEMAS / "evalgate.report.v1.json").read_text())
