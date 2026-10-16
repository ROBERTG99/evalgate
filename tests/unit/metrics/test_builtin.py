from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st

from evalgate.contracts import MetricSpec
from evalgate.metrics.builtin import BUILTIN, to_number
from tests.factories import case, result

json_values = st.recursive(
    st.none() | st.booleans() | st.integers() | st.text(max_size=10),
    lambda children: st.lists(children, max_size=3) | st.dictionaries(st.text(max_size=5), children, max_size=3),
    max_leaves=10,
)


def build(kind: str, **params: Any):
    return BUILTIN[kind](MetricSpec(name="m", kind=kind, params=params))  # type: ignore[arg-type]


@given(json_values)
def test_exact_is_reflexive(value: Any) -> None:
    m = build("exact", actual="output.v", expected="expected.v")
    assert m.score(case(expected={"v": value}), result({"v": value})).value == 1.0


def test_exact_normalize_and_literal() -> None:
    m = build("exact", actual="output.label", expected="expected.label", normalize=True)
    assert m.score(case(expected={"label": "Billing "}), result({"label": "billing"})).value == 1.0
    lit = build("exact", actual="output.label", expected="billing")
    assert lit.score(case(), result({"label": "billing"})).value == 1.0


def test_json_schema() -> None:
    schema = {"type": "object", "required": ["total"], "properties": {"total": {"type": "number"}}}
    m = build("json_schema", actual="output", schema=schema)
    assert m.score(case(), result({"total": 1.5})).value == 1.0
    bad = m.score(case(), result({"total": "1.5"}))
    assert bad.value == 0.0
    assert "total" in bad.details["problem"]
    assert "metric_error" not in bad.details


def test_numeric_tolerance() -> None:
    m = build("numeric_tolerance", actual="output.total", expected="expected.total", abs_tol=0.01)
    assert m.score(case(expected={"total": 10.0}), result({"total": 10.005})).value == 1.0
    assert m.score(case(expected={"total": 10.0}), result({"total": 10.02})).value == 0.0
    assert m.score(case(expected={"total": 10.0}), result({"total": "n/a"})).value == 0.0
    rel = build("numeric_tolerance", actual="output.total", expected="expected.total", rel_tol=0.1)
    assert rel.score(case(expected={"total": 100}), result({"total": "€109.00"})).value == 1.0
    assert to_number("1,234.50 EUR") == 1234.5
    assert to_number(True) is None


def test_contains_all_and_regex() -> None:
    m = build("contains_all", actual="output.answer", expected="expected.key_facts")
    ok = m.score(
        case(expected={"key_facts": ["30 days", "Refund"]}), result({"answer": "Within 30 days for a refund."})
    )
    assert ok.value == 1.0
    miss = m.score(case(expected={"key_facts": ["45 days"]}), result({"answer": "Within 30 days."}))
    assert miss.value == 0.0
    assert miss.details["missing"] == ["45 days"]
    r = build("regex", actual="output.label", pattern="^[a-z_]+$")
    assert r.score(case(), result({"label": "bug_report"})).value == 1.0
    assert r.score(case(), result({"label": "Bug"})).value == 0.0
    assert r.score(case(), result({"label": 3})).value == 0.0


@pytest.mark.parametrize("kind", sorted(BUILTIN))
def test_missing_output_scores_zero_not_crash(kind: str) -> None:
    params: dict[str, Any] = {"pattern": "x"} if kind == "regex" else {}
    if kind == "json_schema":
        params = {"schema": {"type": "object"}}
    m = build(kind, **params)
    s = m.score(case(), result("plain string"))
    assert 0.0 <= s.value <= 1.0


def test_regex_without_pattern_scores_zero() -> None:
    """A missing pattern must not compile the literal string "None" and match it."""
    m = build("regex", actual="output.label", pattern="expected.pattern")
    assert m.score(case(expected={}), result({"label": "None"})).value == 0.0
