import sys
import types
from typing import Any

import pytest

from evalgate.contracts import MetricSpec
from evalgate.metrics.registry import build_metric
from tests.factories import case, result


@pytest.fixture
def fake_ragas(monkeypatch: pytest.MonkeyPatch) -> list[Any]:
    seen: list[Any] = []

    class SingleTurnSample:
        def __init__(self, **kw: Any) -> None:
            self.__dict__.update(kw)

    class FakeFaithfulness:
        def __init__(self, **options: Any) -> None:
            self.options = options

        async def single_turn_ascore(self, sample: Any) -> float:
            seen.append(sample)
            return 0.73

    ragas = types.ModuleType("ragas")
    metrics = types.ModuleType("ragas.metrics")
    metrics.FakeFaithfulness = FakeFaithfulness  # type: ignore[attr-defined]
    schema = types.ModuleType("ragas.dataset_schema")
    schema.SingleTurnSample = SingleTurnSample  # type: ignore[attr-defined]
    for name, module in {
        "ragas": ragas,
        "ragas.metrics": metrics,
        "ragas.dataset_schema": schema,
    }.items():
        monkeypatch.setitem(sys.modules, name, module)
    return seen


def test_maps_fake_score(fake_ragas: list[Any]) -> None:
    m = build_metric(
        MetricSpec(
            name="faith",
            kind="custom",
            params={
                "metric": "ragas:FakeFaithfulness",
                "response": "output.answer",
                "reference": "expected.answer",
                "retrieved_contexts": "output.contexts",
                "pass_at": 0.7,
            },
        )
    )
    s = m.score(
        case(input={"question": "Q?"}, expected={"answer": "ref"}), result({"answer": "ans", "contexts": ["c1", "c2"]})
    )
    assert s.value == 0.73
    assert s.passed
    assert s.details == {"adapter": "ragas", "ragas_metric": "FakeFaithfulness"}
    sample = fake_ragas[0]
    assert (sample.user_input, sample.response, sample.reference) == ("Q?", "ans", "ref")
    assert sample.retrieved_contexts == ["c1", "c2"]


@pytest.mark.extras
def test_real_ragas_non_llm_metric() -> None:
    m = build_metric(MetricSpec(name="em", kind="custom", params={"metric": "ragas:ExactMatch"}))
    assert m.score(case(expected={"answer": "30 days"}), result({"answer": "30 days"})).value == 1.0
    assert m.score(case(expected={"answer": "30 days"}), result({"answer": "45 days"})).value == 0.0


@pytest.mark.extras
def test_real_deepeval_metric() -> None:
    m = build_metric(MetricSpec(name="em", kind="custom", params={"metric": "deepeval:ExactMatchMetric"}))
    assert m.score(case(expected={"answer": "a"}), result({"answer": "a"})).value == 1.0
    assert m.score(case(expected={"answer": "a"}), result({"answer": "b"})).value == 0.0


def test_unknown_adapter_metric() -> None:
    with pytest.raises(KeyError, match="deepeval has no metric"):
        build_metric(MetricSpec(name="x", kind="custom", params={"metric": "deepeval:NoSuchMetric"}))
