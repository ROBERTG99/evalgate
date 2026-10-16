"""Langfuse export (FR-11): one trace per case and one score per metric, via the public ingestion API.

``POST {host}/api/public/ingestion`` with HTTP basic auth (public key, secret key). Event and trace ids
are UUIDv5 of the run and case, so re-exporting the same report is idempotent on the Langfuse side.
A Langfuse outage is retried 3 times and then reported as a warning (``--strict`` turns it into exit 5).
"""

from __future__ import annotations

import os
import time
import uuid
from dataclasses import dataclass
from typing import Any

import httpx

from evalgate.contracts import Report

NAMESPACE = uuid.UUID("6f1f6a52-6c1b-4c5e-9a43-3a1f0f0e7a11")
BATCH_SIZE = 50
MAX_ATTEMPTS = 3


@dataclass
class ExportOutcome:
    ok: bool
    traces: int = 0
    scores: int = 0
    requests: int = 0
    error: str | None = None


def _id(*parts: str) -> str:
    return str(uuid.uuid5(NAMESPACE, "|".join(parts)))


def build_events(report: Report) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    ts = report.created_at
    for case in report.cases:
        trace_id = _id(report.run_id, case.id)
        events.append(
            {
                "id": _id("trace-event", report.run_id, case.id),
                "type": "trace-create",
                "timestamp": ts,
                "body": {
                    "id": trace_id,
                    "name": f"evalgate:{report.suite}",
                    "timestamp": ts,
                    "sessionId": report.run_id,
                    "tags": ["evalgate", report.suite, case.split, report.mode],
                    "metadata": {
                        "case_id": case.id,
                        "passed": case.passed,
                        "cost_usd": case.cost_usd,
                        "latency_ms": case.latency_ms,
                        "error": case.error,
                        "git_sha": report.git_sha,
                    },
                },
            }
        )
        for metric, value in sorted(case.scores.items()):
            events.append(
                {
                    "id": _id("score-event", report.run_id, case.id, metric),
                    "type": "score-create",
                    "timestamp": ts,
                    "body": {
                        "id": _id("score", report.run_id, case.id, metric),
                        "traceId": trace_id,
                        "name": metric,
                        "value": value,
                        "dataType": "NUMERIC",
                        "comment": f"evalgate {report.suite} run {report.run_id}",
                    },
                }
            )
    return events


class LangfuseExporter:
    def __init__(
        self, host: str, public_key: str, secret_key: str, client: httpx.Client | None = None, backoff_s: float = 0.5
    ) -> None:
        self.host = host.rstrip("/")
        self.auth = (public_key, secret_key)
        self.client = client
        self.backoff_s = backoff_s

    @classmethod
    def from_env(cls, host: str | None = None) -> LangfuseExporter:
        return cls(
            host or os.environ.get("LANGFUSE_HOST", "http://localhost:8193"),
            os.environ.get("LANGFUSE_PUBLIC_KEY", ""),
            os.environ.get("LANGFUSE_SECRET_KEY", ""),
        )

    def _post(self, client: httpx.Client, batch: list[dict[str, Any]]) -> None:
        last: str = ""
        for attempt in range(MAX_ATTEMPTS):
            try:
                resp = client.post(
                    f"{self.host}/api/public/ingestion", json={"batch": batch}, auth=self.auth, timeout=10.0
                )
                if resp.status_code in (200, 201, 207):
                    body = resp.json() if resp.content else {}
                    errors = body.get("errors") if isinstance(body, dict) else None
                    if errors:
                        raise RuntimeError(f"langfuse rejected {len(errors)} events: {str(errors[0])[:200]}")
                    return
                last = f"HTTP {resp.status_code}"
                if resp.status_code < 500 and resp.status_code != 429:
                    raise RuntimeError(f"langfuse ingestion failed: {last}")
            except httpx.TransportError as exc:
                last = f"{exc.__class__.__name__}: {exc}"
            if attempt < MAX_ATTEMPTS - 1:
                time.sleep(self.backoff_s * 2**attempt)
        raise RuntimeError(f"langfuse unreachable after {MAX_ATTEMPTS} attempts: {last}")

    def export(self, report: Report) -> ExportOutcome:
        events = build_events(report)
        traces = sum(1 for e in events if e["type"] == "trace-create")
        scores = len(events) - traces
        own = self.client is None
        client = self.client or httpx.Client()
        sent = 0
        try:
            for i in range(0, len(events), BATCH_SIZE):
                self._post(client, events[i : i + BATCH_SIZE])
                sent += 1
        except RuntimeError as exc:
            return ExportOutcome(ok=False, traces=traces, scores=scores, requests=sent, error=str(exc))
        finally:
            if own:
                client.close()
        return ExportOutcome(ok=True, traces=traces, scores=scores, requests=sent)
