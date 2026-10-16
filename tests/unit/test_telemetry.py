import json
import logging
from pathlib import Path
from typing import Any

import pytest

from evalgate import telemetry
from evalgate.contracts import StepRecord, TargetResult
from evalgate.runner import RunOptions, run_suite
from evalgate.suite import load_suite
from tests.factories import rows, write_dataset, write_suite


@pytest.fixture
def otel() -> Any:
    from opentelemetry.sdk.metrics.export import InMemoryMetricReader
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    spans, metrics = InMemorySpanExporter(), InMemoryMetricReader()
    assert telemetry.setup(exporter=spans, metric_reader=metrics)
    yield spans, metrics
    telemetry.shutdown()


def test_span_per_case_and_step(tmp_path: Path, otel: Any) -> None:
    spans, metrics = otel

    async def target(case_input: dict[str, Any]) -> TargetResult:
        steps = [
            StepRecord(node="retrieve", kind="retrieval"),
            StepRecord(
                node="generate",
                kind="llm",
                model="toy-model",
                prompt_version="toy_answer.v1",
                input_tokens=100,
                output_tokens=20,
            ),
        ]
        return TargetResult(output={"label": "a"}, steps=steps)

    data = write_dataset(tmp_path / "d.jsonl", rows(3))
    loaded = load_suite(write_suite(tmp_path / "s.yaml", data), split="test")
    report = run_suite(
        loaded, RunOptions(split="test", home=tmp_path, use_store=False, target=target, resamples=100)
    ).report
    finished = spans.get_finished_spans()
    names = [s.name for s in finished]
    assert names.count("evalgate.run") == 1
    assert names.count("evalgate.case") == 3
    assert names.count("evalgate.target") == 3
    assert names.count("evalgate.step") == 6
    assert names.count("evalgate.metric") == 3
    llm = next(s for s in finished if s.name == "evalgate.step" and s.attributes.get("app.node") == "generate")
    assert llm.attributes["gen_ai.request.model"] == "toy-model"
    assert llm.attributes["gen_ai.usage.input_tokens"] == 100
    assert llm.attributes["app.prompt_version"] == "toy_answer.v1"
    assert llm.attributes["app.run_id"] == report.run_id
    assert llm.attributes["app.cost_usd"] > 0
    run_span = next(s for s in finished if s.name == "evalgate.run")
    case_span = next(s for s in finished if s.name == "evalgate.case")
    assert case_span.parent.span_id == run_span.context.span_id
    data_points = {
        m.name for rm in metrics.get_metrics_data().resource_metrics for sm in rm.scope_metrics for m in sm.metrics
    }
    assert {"evalgate_case_latency_ms", "evalgate_cost_usd_total", "evalgate_tokens_total"} <= data_points


def test_noop_without_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    assert telemetry.setup() is False
    with telemetry.span("x") as s:
        assert s is None


def test_json_logs_carry_ids(capsys: pytest.CaptureFixture[str]) -> None:
    formatter = telemetry.JsonFormatter()
    record = logging.LogRecord("evalgate", logging.WARNING, __file__, 1, "store down", None, None)
    record.run_id = "r-1"  # type: ignore[attr-defined]
    record.case_id = "c-1"  # type: ignore[attr-defined]
    payload = json.loads(formatter.format(record))
    assert payload["run_id"] == "r-1" and payload["case_id"] == "c-1" and payload["level"] == "WARNING"


def test_gauge_and_counter_semantics() -> None:
    telemetry.reset_counters()
    telemetry.count("evalgate_gate_last_decision", 1.0, suite="s")
    telemetry.count("evalgate_gate_last_decision", 0.0, suite="s")
    telemetry.count("evalgate_cache_hits_total")
    telemetry.count("evalgate_cache_hits_total")
    c = telemetry.counters()
    assert c['evalgate_gate_last_decision{suite="s"}'] == 0.0
    assert c["evalgate_cache_hits_total"] == 2.0


def test_env_endpoint_alone_enables_export(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[bool] = []
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://127.0.0.1:9")
    monkeypatch.setattr(telemetry, "setup", lambda enabled=False, **kw: calls.append(enabled) or True)
    monkeypatch.setattr(telemetry, "shutdown", lambda: calls.append(True))
    data = write_dataset(tmp_path / "d.jsonl", rows(1))
    loaded = load_suite(write_suite(tmp_path / "s.yaml", data), split="test")
    run_suite(loaded, RunOptions(split="test", home=tmp_path, use_store=False, resamples=10))
    assert calls == [False, True]  # setup consulted without --otel, then flushed
    monkeypatch.undo()
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://127.0.0.1:9")
    assert telemetry.setup() is True
    telemetry.shutdown()


def test_judge_span_carries_usage_cost_and_run_id(otel: Any) -> None:
    import asyncio

    from evalgate.llm.gateway import Gateway
    from tests.unit.llm.test_gateway import VERDICT, Scripted, no_sleep, request

    spans, _ = otel
    gw = Gateway(Scripted([VERDICT]), provider_name="anthropic", budget_usd=1.0, sleep=no_sleep)

    async def call() -> None:
        with telemetry.run_context("0190-run"):
            await gw.complete(request())

    asyncio.run(call())
    judge = next(s for s in spans.get_finished_spans() if s.name == "evalgate.judge")
    assert judge.attributes["app.run_id"] == "0190-run"
    assert judge.attributes["gen_ai.usage.input_tokens"] > 0
    assert judge.attributes["gen_ai.usage.output_tokens"] > 0
    assert judge.attributes["app.cost_usd"] > 0
    assert judge.attributes["gen_ai.response.model"] == "claude-haiku-5-5"


def test_logs_carry_the_current_run_id() -> None:
    record = logging.LogRecord("evalgate", logging.WARNING, __file__, 1, "store down", None, None)
    with telemetry.run_context("0190-run"):
        payload = json.loads(telemetry.JsonFormatter().format(record))
    assert payload["run_id"] == "0190-run"
