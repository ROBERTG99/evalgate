"""OpenTelemetry spans and JSON logs (§14). No-ops unless ``--otel`` or ``OTEL_EXPORTER_OTLP_ENDPOINT``.

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
from typing import Any

_tracer: Any = None
_meter_counts: dict[str, float] = {}
log = logging.getLogger("evalgate")


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
        return json.dumps(payload, ensure_ascii=False)


def configure_logging() -> None:
    if any(isinstance(h.formatter, JsonFormatter) for h in log.handlers):
        return
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(JsonFormatter())
    log.addHandler(handler)
    log.setLevel(os.environ.get("LOG_LEVEL", "WARNING").upper())
    log.propagate = False


def setup(enabled: bool = False, exporter: Any = None) -> bool:
    """Enable tracing. ``exporter`` overrides the OTLP exporter (tests pass an in-memory one)."""
    global _tracer
    endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip()
    if not (enabled or endpoint or exporter is not None):
        _tracer = None
        return False
    try:
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor, SimpleSpanProcessor
    except ImportError:
        log.warning("opentelemetry-sdk is not installed; install evalgate[otel] to emit spans")
        _tracer = None
        return False
    provider = TracerProvider(resource=Resource.create({"service.name": "evalgate"}))
    if exporter is not None:
        provider.add_span_processor(SimpleSpanProcessor(exporter))
    else:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    _tracer = provider.get_tracer("evalgate")
    return True


def shutdown() -> None:
    global _tracer
    _tracer = None


def enabled() -> bool:
    return _tracer is not None


@contextmanager
def span(name: str, **attributes: Any) -> Iterator[Any]:
    if _tracer is None:
        yield None
        return
    clean = {k.replace("__", "."): v for k, v in attributes.items() if v is not None}
    with _tracer.start_as_current_span(name, attributes=clean) as current:
        yield current


def count(name: str, value: float = 1.0, **labels: str) -> None:
    """In-process counters (``evalgate_*``); exported in the report extensions and the Prometheus text."""
    inner = ",".join(f'{k}="{v}"' for k, v in sorted(labels.items()))
    key = f"{name}{{{inner}}}" if inner else name
    _meter_counts[key] = _meter_counts.get(key, 0.0) + value


def counters() -> dict[str, float]:
    return dict(_meter_counts)


def reset_counters() -> None:
    _meter_counts.clear()
