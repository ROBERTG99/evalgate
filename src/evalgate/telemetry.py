"""OpenTelemetry spans and JSON logs. No-ops unless ``--otel`` or ``OTEL_EXPORTER_OTLP_ENDPOINT``.

Spans: ``evalgate.run`` > ``evalgate.case`` > ``evalgate.target`` / ``evalgate.step`` / ``evalgate.metric``
/ ``evalgate.judge``, with ``gen_ai.*`` and ``app.*`` attributes. The collector being down only drops spans.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

_tracer: Any = None
_meter: Any = None
_tracer_provider: Any = None
_meter_provider: Any = None
_instruments: dict[str, Any] = {}
_meter_counts: dict[str, float] = {}
HISTOGRAMS = {"evalgate_case_latency_ms"}
GAUGES = {"evalgate_gate_last_decision"}
log = logging.getLogger("evalgate")
_run_id: ContextVar[str | None] = ContextVar("evalgate_run_id", default=None)


@contextmanager
def run_context(run_id: str) -> Iterator[None]:
    """Tag spans and log lines started inside (including tasks created inside) with ``app.run_id``."""
    token = _run_id.set(run_id)
    try:
        yield
    finally:
        _run_id.reset(token)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for key in ("run_id", "case_id", "metric", "event"):
            if hasattr(record, key):
                payload[key] = getattr(record, key)
        if "run_id" not in payload and _run_id.get() is not None:
            payload["run_id"] = _run_id.get()
        return json.dumps(payload, ensure_ascii=False)


def configure_logging() -> None:
    if any(isinstance(h.formatter, JsonFormatter) for h in log.handlers):
        return
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(JsonFormatter())
    log.addHandler(handler)
    log.setLevel(os.environ.get("LOG_LEVEL", "WARNING").upper())
    log.propagate = False


def setup(enabled: bool = False, exporter: Any = None, metric_reader: Any = None) -> bool:
    """Enable tracing and metrics. ``exporter``/``metric_reader`` override OTLP (tests pass in-memory ones)."""
    global _tracer, _meter, _tracer_provider, _meter_provider
    endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip()
    if not (enabled or endpoint or exporter is not None or metric_reader is not None):
        _tracer = None
        _meter = None
        return False
    try:
        from opentelemetry.sdk.metrics import MeterProvider
        from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor, SimpleSpanProcessor
    except ImportError:
        log.warning("opentelemetry-sdk is not installed; install evalgate[otel] to emit spans")
        _tracer = None
        return False
    import uuid

    # Traces get one instance id per process. Metrics keep a stable identity so successive CLI runs write the
    # same Prometheus series: GateFlapping needs `changes()` over one gauge, and `increase()` handles counter restarts.
    detected = Resource.create({"service.name": "evalgate"})  # newer SDKs add a random service.instance.id
    metric_resource = Resource({k: v for k, v in detected.attributes.items() if k != "service.instance.id"})
    trace_resource = metric_resource.merge(Resource({"service.instance.id": str(uuid.uuid4())}))
    _tracer_provider = TracerProvider(resource=trace_resource)
    if exporter is not None:
        _tracer_provider.add_span_processor(SimpleSpanProcessor(exporter))
    else:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

        _tracer_provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    if metric_reader is None and exporter is None:
        from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter

        metric_reader = PeriodicExportingMetricReader(OTLPMetricExporter(), export_interval_millis=5000)
    readers = [metric_reader] if metric_reader is not None else []
    _meter_provider = MeterProvider(resource=metric_resource, metric_readers=readers)
    _meter = _meter_provider.get_meter("evalgate")
    _instruments.clear()
    _tracer = _tracer_provider.get_tracer("evalgate")
    return True


def shutdown() -> None:
    """Flush and stop exporters. A collector that is down only loses spans; the run is unaffected."""
    global _tracer, _meter, _tracer_provider, _meter_provider
    for provider in (_tracer_provider, _meter_provider):
        if provider is not None:
            try:
                provider.shutdown()
            except Exception as exc:  # pragma: no cover - exporter failures never fail a run
                log.warning("telemetry shutdown failed: %s", exc)
    _tracer = _meter = _tracer_provider = _meter_provider = None


def enabled() -> bool:
    return _tracer is not None


@contextmanager
def span(name: str, **attributes: Any) -> Iterator[Any]:
    if _tracer is None:
        yield None
        return
    clean = {k.replace("__", "."): v for k, v in attributes.items() if v is not None}
    if "app.run_id" not in clean and _run_id.get() is not None:
        clean["app.run_id"] = _run_id.get()
    with _tracer.start_as_current_span(name, attributes=clean) as current:
        yield current


def count(name: str, value: float = 1.0, **labels: str) -> None:
    """Record ``evalgate_*`` metrics: kept in-process (``counters()``) and exported over OTLP when enabled."""
    inner = ",".join(f'{k}="{v}"' for k, v in sorted(labels.items()))
    key = f"{name}{{{inner}}}" if inner else name
    _meter_counts[key] = value if name in GAUGES else _meter_counts.get(key, 0.0) + value
    if _meter is None:
        return
    instrument = _instruments.get(name)
    if instrument is None:
        if name in HISTOGRAMS:
            instrument = _meter.create_histogram(name)  # the name carries the unit
        elif name in GAUGES:
            instrument = _meter.create_gauge(name)
        else:
            instrument = _meter.create_counter(name)
        _instruments[name] = instrument
    if name in HISTOGRAMS:
        instrument.record(value, attributes=labels)
    elif name in GAUGES:
        instrument.set(value, attributes=labels)
    else:
        instrument.add(value, attributes=labels)


def counters() -> dict[str, float]:
    return dict(_meter_counts)


def reset_counters() -> None:
    _meter_counts.clear()
