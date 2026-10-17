import json
from pathlib import Path

import pytest
import yaml

from evalgate.adapters.promptfoo import import_promptfoo
from evalgate.errors import InvalidInputError
from evalgate.suite import load_suite

ROOT = Path(__file__).resolve().parents[3]
SAMPLE = ROOT / "evals/datasets/promptfoo/promptfooconfig.yaml"


def test_assert_mapping(tmp_path: Path) -> None:
    suite_path, dataset_path, unsupported = import_promptfoo(SAMPLE, tmp_path, name="pf")
    suite = yaml.safe_load(suite_path.read_text())
    kinds = {m["name"]: m["kind"] for m in suite["metrics"]}
    assert kinds == {
        "equals": "exact",
        "contains": "contains_all",
        "regex": "regex",
        "is_json": "json_schema",
        "llm_rubric": "judge",
    }
    judge = next(m for m in suite["metrics"] if m["kind"] == "judge")
    assert judge["gate"] is False
    assert sorted(set(unsupported)) == ["javascript", "similar"]
    rows = [json.loads(x) for x in dataset_path.read_text().splitlines()]
    assert len(rows) == 12
    flagged = [r for r in rows if r["meta"]["unsupported_asserts"]]
    assert {a for r in flagged for a in r["meta"]["unsupported_asserts"]} == {"javascript", "similar"}
    assert rows[0]["input"] == {"text": rows[0]["meta"]["vars"]["text"]}
    assert suite["target"]["http"]["headers"] == {"X-Toy-Version": "v1"}
    loaded = load_suite(suite_path)
    assert loaded.suite.metrics[0].params["actual"] == "output.label"


def test_base_url_override(tmp_path: Path) -> None:
    suite_path, _, _ = import_promptfoo(SAMPLE, tmp_path, base_url="http://127.0.0.1:9999")
    assert yaml.safe_load(suite_path.read_text())["target"]["http"]["url"] == "http://127.0.0.1:9999/classify"


def test_non_http_provider_rejected(tmp_path: Path) -> None:
    cfg = tmp_path / "promptfooconfig.yaml"
    cfg.write_text(yaml.safe_dump({"providers": ["openai:gpt-x"], "tests": [{"vars": {"a": 1}}]}))
    with pytest.raises(InvalidInputError, match="only the http provider"):
        import_promptfoo(cfg, tmp_path)


@pytest.mark.parametrize(("asserts", "insensitive"), [(["contains"], False), (["icontains"], True)])
def test_contains_keeps_promptfoo_case_sensitivity(tmp_path: Path, asserts: list[str], insensitive: bool) -> None:
    config = {
        "providers": [{"id": "http", "config": {"url": "http://localhost:8110/classify", "body": {"text": "{{q}}"}}}],
        "tests": [{"vars": {"q": "x"}, "assert": [{"type": kind, "value": "Refund"} for kind in asserts]}],
    }
    path = tmp_path / "promptfooconfig.yaml"
    path.write_text(yaml.safe_dump(config))
    suite_path, _, _ = import_promptfoo(path, tmp_path / "out", name="pf")
    metric = next(m for m in yaml.safe_load(suite_path.read_text())["metrics"] if m["name"] == "contains")
    assert metric["params"]["case_insensitive"] is insensitive
