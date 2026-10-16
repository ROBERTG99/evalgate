"""FastAPI toy targets: ``/classify``, ``/extract`` and ``/answer`` as v1, v2 and 50 catalogued variants.

Select a version with ``X-Toy-Version: v1|v2`` or a variant with ``X-Toy-Variant: var-NN``. Unknown
versions or variants return 400. ``/metrics`` exposes Prometheus counters.
"""

from __future__ import annotations

import asyncio
import threading
import time
from collections import defaultdict
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Request, Response
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel, ConfigDict, Field

from toy_targets import systems, variants

VERSIONS = {"v1", "v2"}


class ClassifyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=10_000)


class ExtractRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    document: str = Field(min_length=1, max_length=50_000)


class AnswerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(min_length=1, max_length=2_000)


class Step(BaseModel):
    node: str
    kind: str
    model: str | None = None
    prompt_version: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    args: dict[str, Any] | None = None
    status: str = "ok"


class ClassifyResponse(BaseModel):
    label: str
    confidence: float
    steps: list[Step]


class ExtractResponse(BaseModel):
    invoice_number: str
    date: str
    total: float
    currency: str
    vendor: str
    steps: list[Step]


class AnswerResponse(BaseModel):
    answer: str
    citations: list[str]
    steps: list[Step]


class Metrics:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.requests: dict[tuple[str, str, int], int] = defaultdict(int)
        self.latency_sum: dict[str, float] = defaultdict(float)
        self.latency_count: dict[str, int] = defaultdict(int)

    def observe(self, endpoint: str, version: str, status: int, seconds: float) -> None:
        with self.lock:
            self.requests[(endpoint, version, status)] += 1
            self.latency_sum[endpoint] += seconds
            self.latency_count[endpoint] += 1

    def render(self) -> str:
        lines = [
            "# HELP toy_requests_total Requests by endpoint, version and status.",
            "# TYPE toy_requests_total counter",
        ]
        with self.lock:
            for (endpoint, version, status), n in sorted(self.requests.items()):
                lines.append(f'toy_requests_total{{endpoint="{endpoint}",version="{version}",status="{status}"}} {n}')
            lines += [
                "# HELP toy_request_duration_seconds Request latency.",
                "# TYPE toy_request_duration_seconds summary",
            ]
            for endpoint in sorted(self.latency_count):
                lines.append(
                    f'toy_request_duration_seconds_sum{{endpoint="{endpoint}"}} {self.latency_sum[endpoint]:.6f}'
                )
                lines.append(
                    f'toy_request_duration_seconds_count{{endpoint="{endpoint}"}} {self.latency_count[endpoint]}'
                )
        return "\n".join(lines) + "\n"


VERSION_HEADER = Header(default=None, json_schema_extra={"enum": sorted(VERSIONS)}, description="v1 (default) or v2")


def variant_header(system: str) -> Any:
    ids = sorted(k for k, v in variants.catalogue().items() if v["system"] == system)
    return Header(default=None, json_schema_extra={"enum": ids}, description=f"A catalogued /{system} variant")


def create_app() -> FastAPI:
    app = FastAPI(
        title="evalgate toy targets",
        version="1.0.0",
        description="Deterministic toy AI systems (synthetic data, rule-based, no model calls).",
    )
    metrics = Metrics()

    def resolve(system: str, version: str | None, variant: str | None) -> tuple[str, dict[str, Any] | None]:
        if version is not None and version not in VERSIONS:
            raise HTTPException(400, f"unknown version {version!r}; use v1 or v2")
        if variant is not None:
            entry = variants.catalogue().get(variant)
            if entry is None or entry["system"] != system:
                raise HTTPException(400, f"unknown variant {variant!r} for /{system}")
            return variant, entry
        version = version or "v1"
        if version not in VERSIONS:
            raise HTTPException(400, f"unknown version {version!r}; use v1 or v2")
        return version, None

    async def handle(system: str, payload: str, version: str | None, variant: str | None) -> dict[str, Any]:
        start = time.perf_counter()
        label = "invalid"
        try:
            label, entry = resolve(system, version, variant)
            if entry is not None:
                out = variants.apply(system, payload, entry)
                delay = variants.latency_ms(entry)
                if delay:
                    await asyncio.sleep(delay / 1000)
            elif system == "classify":
                out = systems.classify(payload, label)
            elif system == "extract":
                out = systems.extract(payload, label)
            else:
                out = systems.answer(payload, label)
            out.pop("_subtotal", None)
            metrics.observe(system, label, 200, time.perf_counter() - start)
            return out
        except HTTPException as exc:
            metrics.observe(system, label, exc.status_code, time.perf_counter() - start)
            raise

    @app.post("/classify", responses={200: {"model": ClassifyResponse}, 400: {"description": "Unknown version"}})
    async def classify(
        body: ClassifyRequest,
        x_toy_version: str | None = VERSION_HEADER,
        x_toy_variant: str | None = variant_header("classify"),
    ) -> JSONResponse:
        return JSONResponse(await handle("classify", body.text, x_toy_version, x_toy_variant))

    @app.post("/extract", responses={200: {"model": ExtractResponse}, 400: {"description": "Unknown version"}})
    async def extract(
        body: ExtractRequest,
        x_toy_version: str | None = VERSION_HEADER,
        x_toy_variant: str | None = variant_header("extract"),
    ) -> JSONResponse:
        return JSONResponse(await handle("extract", body.document, x_toy_version, x_toy_variant))

    @app.post("/answer", responses={200: {"model": AnswerResponse}, 400: {"description": "Unknown version"}})
    async def answer(
        body: AnswerRequest,
        x_toy_version: str | None = VERSION_HEADER,
        x_toy_variant: str | None = variant_header("answer"),
    ) -> JSONResponse:
        return JSONResponse(await handle("answer", body.question, x_toy_version, x_toy_variant))

    @app.get("/healthz")
    async def healthz() -> dict[str, Any]:
        return {"status": "ok", "documents": len(systems.corpus()), "variants": len(variants.catalogue())}

    @app.get("/metrics", response_class=PlainTextResponse)
    async def prometheus() -> Response:
        return PlainTextResponse(metrics.render(), media_type="text/plain; version=0.0.4")

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException) -> JSONResponse:
        return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)

    return app


app = create_app()
