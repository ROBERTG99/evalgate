import asyncio
from typing import Any, TypedDict

import pytest

from evalgate.contracts import TargetSpec
from evalgate.targets import build_target

pytestmark = pytest.mark.extras


class State(TypedDict, total=False):
    question: str
    docs: list[str]
    answer: str
    _usage: dict[str, Any]


def retrieve(state: State) -> State:
    return {"docs": ["Returns are accepted within 30 days."]}


def generate(state: State) -> State:
    return {"answer": state["docs"][0], "_usage": {"model": "toy-model", "input_tokens": 50, "output_tokens": 9}}


def build_graph() -> Any:
    from langgraph.graph import END, START, StateGraph

    g = StateGraph(State)
    g.add_node("retrieve", retrieve)
    g.add_node("generate", generate)
    g.add_edge(START, "retrieve")
    g.add_edge("retrieve", "generate")
    g.add_edge("generate", END)
    return g.compile()


GRAPH = build_graph()


def test_one_step_per_node() -> None:
    target = build_target(TargetSpec(langgraph="tests.integration.targets.test_langgraph:GRAPH"))
    result = asyncio.run(target({"question": "How long can I return items?"}))
    assert [s.node for s in result.steps] == ["retrieve", "generate"]
    assert result.steps[1].model == "toy-model"
    assert result.steps[1].kind == "llm"
    assert result.steps[1].input_tokens == 50
    assert isinstance(result.output, dict)
    assert result.output["answer"] == "Returns are accepted within 30 days."
    assert "_usage" not in result.output
