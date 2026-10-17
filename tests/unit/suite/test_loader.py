import json
import subprocess
import sys
from pathlib import Path

import pytest

from evalgate.errors import InvalidInputError
from evalgate.suite import load_dataset, load_suite
from evalgate.suite.loader import interpolate
from tests.factories import rows, write_dataset, write_suite

ROOT = Path(__file__).resolve().parents[3]


def test_unknown_key_exit_2(tmp_path: Path) -> None:
    data = write_dataset(tmp_path / "d.jsonl", rows(3))
    suite = write_suite(tmp_path / "s.yaml", data)
    text = suite.read_text().replace("metrics:", "metircs:")
    suite.write_text(text)
    proc = subprocess.run(
        [sys.executable, "-m", "evalgate.cli", "run", str(suite), "--split", "test", "--out", str(tmp_path / "r.json")],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 2
    assert str(suite) in proc.stderr
    assert "$.metircs" in proc.stderr
    assert "unknown key 'metircs'" in proc.stderr


def test_duplicate_id_line(tmp_path: Path) -> None:
    data_rows = rows(40)
    data_rows[36]["id"] = data_rows[10]["id"]
    path = write_dataset(tmp_path / "d.jsonl", data_rows)
    with pytest.raises(InvalidInputError) as info:
        load_dataset(path)
    assert info.value.location == "line 37"
    assert "duplicate id 'r-0010'" in info.value.problem
    assert info.value.exit_code == 2
    assert str(path) in str(info.value)


def test_dataset_bad_row_names_line_and_path(tmp_path: Path) -> None:
    data_rows = rows(3)
    data_rows[1]["split"] = "train"
    path = write_dataset(tmp_path / "d.jsonl", data_rows)
    with pytest.raises(InvalidInputError) as info:
        load_dataset(path)
    assert info.value.location == "line 2 $.split"


def test_invalid_json_line(tmp_path: Path) -> None:
    path = tmp_path / "d.jsonl"
    path.write_text(json.dumps(rows(1)[0]) + "\n{not json\n")
    with pytest.raises(InvalidInputError, match="line 2"):
        load_dataset(path)


def test_nested_error_json_path(tmp_path: Path) -> None:
    data = write_dataset(tmp_path / "d.jsonl", rows(3))
    suite = write_suite(tmp_path / "s.yaml", data, concurrency=0)
    with pytest.raises(InvalidInputError) as info:
        load_suite(suite)
    assert info.value.location == "$.concurrency"


def test_target_exactly_one(tmp_path: Path) -> None:
    data = write_dataset(tmp_path / "d.jsonl", rows(3))
    suite = write_suite(tmp_path / "s.yaml", data, target={"python": "a:b", "langgraph": "c:d"})
    with pytest.raises(InvalidInputError, match="exactly one"):
        load_suite(suite)


def test_selector_root_validated(tmp_path: Path) -> None:
    data = write_dataset(tmp_path / "d.jsonl", rows(3))
    metrics = [{"name": "acc", "kind": "exact", "params": {"actual": "result.label", "expected": "x"}}]
    suite = write_suite(tmp_path / "s.yaml", data, metrics=metrics)
    with pytest.raises(InvalidInputError) as info:
        load_suite(suite)
    assert info.value.location == "$.metrics[0].params.actual"


def test_split_filter_and_undeclared_split(tmp_path: Path) -> None:
    data = write_dataset(tmp_path / "d.jsonl", rows(3, split="dev") + [{**rows(1)[0], "id": "x-1"}])
    suite = write_suite(tmp_path / "s.yaml", data, splits=["dev"])
    loaded = load_suite(suite, split="dev")
    assert [c.id for c in loaded.cases] == ["r-0000", "r-0001", "r-0002"]
    with pytest.raises(InvalidInputError, match="not declared"):
        load_suite(suite, split="test")


def test_interpolation_only_in_target(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TOYS", "http://localhost:9999")
    assert interpolate({"url": "${TOYS:-http://x}/a", "h": ["${MISSING:-dflt}"]}) == {
        "url": "http://localhost:9999/a",
        "h": ["dflt"],
    }
    data = write_dataset(tmp_path / "d.jsonl", rows(2))
    suite = write_suite(
        tmp_path / "s.yaml",
        data,
        target={"http": {"url": "${TOYS:-http://localhost:8110}/classify"}},
        description="${TOYS}",
    )
    loaded = load_suite(suite)
    assert loaded.suite.target.http is not None
    assert loaded.suite.target.http.url == "http://localhost:9999/classify"
    assert loaded.suite.description == "${TOYS}"


def test_invalid_yaml_reports_line(tmp_path: Path) -> None:
    path = tmp_path / "s.yaml"
    path.write_text("schema: evalgate.suite.v1\nname: [unclosed\n")
    with pytest.raises(InvalidInputError, match="invalid YAML"):
        load_suite(path)


def test_missing_files(tmp_path: Path) -> None:
    with pytest.raises(InvalidInputError, match="file not found"):
        load_suite(tmp_path / "nope.yaml")
    suite = write_suite(tmp_path / "s.yaml", tmp_path / "missing.jsonl")
    with pytest.raises(InvalidInputError, match="dataset file not found"):
        load_suite(suite)
