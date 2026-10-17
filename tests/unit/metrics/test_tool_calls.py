from typing import Any

from hypothesis import given
from hypothesis import strategies as st

from evalgate.contracts import MetricSpec
from evalgate.metrics.builtin import ToolCallsMetric
from tests.factories import case, result

EXPECTED = [{"name": "search_faq"}, {"name": "read_doc", "args_subset": {"doc_id": "faq-07"}}]


def metric(**params: Any) -> ToolCallsMetric:
    return ToolCallsMetric(MetricSpec(name="tools", kind="tool_calls", params=params))


def score(steps: list[dict[str, Any]], **params: Any) -> float:
    c = case(expected={"tools": EXPECTED})
    return metric(**params).score(c, result({"steps": steps})).value


def test_args_subset_in_order() -> None:
    steps = [
        {"node": "search_faq", "kind": "tool", "args": {"query": "returns"}},
        {"node": "read_doc", "kind": "tool", "args": {"doc_id": "faq-07", "max_chars": 500}},
        {"node": "generate", "kind": "llm"},
    ]
    assert score(steps) == 1.0


def test_wrong_order_or_args_fail() -> None:
    reversed_steps = [
        {"node": "read_doc", "kind": "tool", "args": {"doc_id": "faq-07"}},
        {"node": "search_faq", "kind": "tool", "args": {}},
    ]
    assert score(reversed_steps) == 0.0
    wrong_arg = [
        {"node": "search_faq", "kind": "tool"},
        {"node": "read_doc", "kind": "tool", "args": {"doc_id": "faq-08"}},
    ]
    assert score(wrong_arg) == 0.0
    assert score([{"node": "search_faq", "kind": "tool"}]) == 0.0


def test_extra_calls_allowed_unless_exact_sequence() -> None:
    steps = [
        {"name": "search_faq", "arguments": {}},
        {"name": "search_faq", "arguments": {}},
        {"name": "read_doc", "arguments": {"doc_id": "faq-07"}},
    ]
    assert score(steps) == 1.0
    assert score(steps, exact_sequence=True) == 0.0


@given(st.lists(st.sampled_from(["search_faq", "read_doc", "other"]), max_size=8))
def test_subsequence_property(names: list[str]) -> None:
    steps = [{"node": n, "kind": "tool", "args": {"doc_id": "faq-07"}} for n in names]
    expected_hit = False
    try:
        i = names.index("search_faq")
        expected_hit = "read_doc" in names[i + 1 :]
    except ValueError:
        expected_hit = False
    assert score(steps) == (1.0 if expected_hit else 0.0)
