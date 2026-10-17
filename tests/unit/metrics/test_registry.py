from pathlib import Path

import pytest

import evalgate
from evalgate.contracts import MetricScore, MetricSpec
from evalgate.metrics.registry import build_metric, registered, unregister
from evalgate.runner import RunOptions, run_suite
from evalgate.suite import load_suite
from tests.factories import case, result, rows, write_dataset, write_suite


def test_custom_metric() -> None:
    @evalgate.metric("len_ok")
    def len_ok(c, r):  # type: ignore[no-untyped-def]
        return len(r.output["text"]) < 5

    try:
        m = build_metric(MetricSpec(name="short", kind="custom", params={"metric": "len_ok"}))
        assert m.score(case(), result({"text": "abc"})).value == 1.0
        assert m.score(case(), result({"text": "abcdef"})).value == 0.0
        assert "len_ok" in registered()
    finally:
        unregister("len_ok")


def test_custom_metric_returning_metric_score_and_class() -> None:
    @evalgate.metric("always_half")
    def half(c, r, params):  # type: ignore[no-untyped-def]
        return MetricScore(name="ignored", value=params["v"], passed=True, details={"k": 1})

    @evalgate.metric("cls_metric")
    class Cls:
        def __init__(self, params):  # type: ignore[no-untyped-def]
            self.params = params

        def score(self, c, r):  # type: ignore[no-untyped-def]
            return 0.25

    try:
        m = build_metric(MetricSpec(name="h", kind="custom", params={"metric": "always_half", "v": 0.5}))
        s = m.score(case(), result({}))
        assert (s.name, s.value, s.details) == ("h", 0.5, {"k": 1})
        k = build_metric(MetricSpec(name="k", kind="custom", params={"metric": "cls_metric"}))
        assert k.score(case(), result({})).value == 0.25
    finally:
        unregister("always_half")
        unregister("cls_metric")


def test_duplicate_registration_rejected() -> None:
    @evalgate.metric("dupe")
    def a(c, r):  # type: ignore[no-untyped-def]
        return 1.0

    try:
        with pytest.raises(ValueError, match="already registered"):
            evalgate.metric("dupe")(lambda c, r: 0.0)
    finally:
        unregister("dupe")


def test_unknown_custom_metric_is_invalid_input(tmp_path: Path) -> None:
    data = write_dataset(tmp_path / "d.jsonl", rows(2))
    suite = write_suite(
        tmp_path / "s.yaml", data, metrics=[{"name": "x", "kind": "custom", "params": {"metric": "nope"}}]
    )
    from evalgate.errors import InvalidInputError

    with pytest.raises(InvalidInputError, match="unknown custom metric"):
        run_suite(load_suite(suite), RunOptions(home=tmp_path, use_store=False))


def test_example_word_budget_via_plugins(tmp_path: Path) -> None:
    data = write_dataset(tmp_path / "d.jsonl", rows(3))
    suite = write_suite(
        tmp_path / "s.yaml",
        data,
        plugins=["examples.metrics.word_budget"],
        metrics=[
            {
                "name": "brevity",
                "kind": "custom",
                "params": {"metric": "word_budget", "field": "text", "max_words": 1},
                "threshold": 0.5,
            }
        ],
    )
    report = run_suite(load_suite(suite), RunOptions(home=tmp_path, use_store=False, resamples=100)).report
    assert report.metrics["brevity"].value == 1.0
