import pytest
import yaml

from evalgate.accounting import percentile, price_steps, price_table, step_cost, unpriced_models
from evalgate.contracts import StepRecord


def test_cost_formula() -> None:
    # claude-haiku-5-5: USD 0.10 per million input tokens and 0.50 per million output tokens
    assert step_cost("claude-haiku-5-5", 1_000_000, 0) == pytest.approx(0.10)
    assert step_cost("claude-haiku-5-5", 1200, 300) == pytest.approx((1200 * 0.10 + 300 * 0.50) / 1e6)
    assert step_cost("claude-opus-5-5", 1000, 1000) == pytest.approx((1000 * 4.0 + 1000 * 20.0) / 1e6)
    assert step_cost("toy-model", 140, 4) == pytest.approx((140 * 0.5 + 4 * 1.5) / 1e6)
    assert step_cost("unknown-model", 1000, 1000) == 0.0
    assert step_cost(None, 1000, 1000) == 0.0


def test_price_yaml_has_source_and_date() -> None:
    from importlib import resources

    text = resources.files("evalgate").joinpath("pricing.yaml").read_text()
    data = yaml.safe_load(text)
    assert data["source"].startswith("https://")
    assert str(data["retrieved"]) == "2026-10-16"
    assert "claude-haiku-5-5" in price_table()


def test_price_steps_fills_missing_costs_only() -> None:
    steps = [
        StepRecord(node="a", kind="llm", model="toy-model", input_tokens=100, output_tokens=10),
        StepRecord(node="b", kind="llm", model="toy-model", input_tokens=100, output_tokens=10, cost_usd=1.0),
        StepRecord(node="c", kind="llm", model="mystery", input_tokens=5, output_tokens=5),
    ]
    priced = price_steps(steps)
    assert priced[0].cost_usd == pytest.approx(step_cost("toy-model", 100, 10))
    assert priced[1].cost_usd == 1.0
    assert unpriced_models(priced) == {"mystery"}


def test_percentile_matches_numpy_linear() -> None:
    import numpy as np

    values = [5.0, 1.0, 9.0, 3.0, 7.0, 2.0]
    for q in (50, 95, 0, 100):
        assert percentile(values, q) == pytest.approx(float(np.percentile(values, q)))
    assert percentile([], 95) == 0.0
    assert percentile([4.0], 95) == 4.0
