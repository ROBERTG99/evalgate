"""Shared judge plumbing for one run: rubric loading, cache, gateway, concurrency and counters."""

from __future__ import annotations

import asyncio
import hashlib
import sys
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from typing import Any

from evalgate import config, telemetry
from evalgate.budget import enforce_estimate, estimate_judge_cost
from evalgate.contracts import JudgeVerdict, Rubric
from evalgate.contracts.judge import VERDICT_SCHEMA_NAME
from evalgate.errors import InvalidInputError
from evalgate.llm.cassette import request_digest, request_key
from evalgate.llm.fake import FAKE_MODEL
from evalgate.llm.types import LLMRequest

EFFORT = {"judge": "low", "judge_hard": "medium"}
MAX_TOKENS = 4096


@dataclass
class LoadedRubric:
    rubric: Rubric
    path: Path
    prompt_text: str
    prompt_version: str
    prompt_sha256: str

    @property
    def label(self) -> str:
        return f"{self.rubric.name}.v{self.rubric.version}"


@dataclass
class JudgeCall:
    verdict: JudgeVerdict
    cost_usd: float
    source: str
    model: str
    cached: bool


def resolve_prompt(ref: str, rubric_path: Path) -> Path:
    candidates = [Path(ref), rubric_path.parent / ref]
    for p in candidates:
        if p.is_file():
            return p
    packaged = resources.files("evalgate").joinpath("prompts").joinpath(Path(ref).name)
    if packaged.is_file():
        return Path(str(packaged))
    raise InvalidInputError(str(rubric_path), "$.prompt", f"prompt file {ref!r} not found")


def load_rubric(path: Path) -> LoadedRubric:
    from evalgate.suite.loader import parse_model, read_yaml

    rubric = parse_model(Rubric, read_yaml(path), path)
    prompt_path = resolve_prompt(rubric.prompt, path)
    text = prompt_path.read_text(encoding="utf-8")
    version = prompt_path.name.removesuffix(".md")
    expected = f"judge_{rubric.name}.v"
    if not version.startswith("judge_"):
        raise InvalidInputError(
            str(path), "$.prompt", f"prompt must be named judge_<rubric>.v<N>.md (expected {expected}N)"
        )
    return LoadedRubric(rubric, path, text, version, hashlib.sha256(text.encode("utf-8")).hexdigest())


@dataclass
class MetricDiagnostics:
    rubric: str = ""
    prompt_version: str = ""
    route: str = ""
    verdicts: dict[str, int] = field(default_factory=dict)
    position_inconsistent: int = 0
    injections_blocked: int = 0
    errors: int = 0
    cases: int = 0


class JudgeContext:
    def __init__(self, gateway: Any, cache: Any, base_dir: Path | None = None) -> None:
        self.gateway = gateway
        self.cache = cache
        self.base_dir = base_dir or Path.cwd()
        self.sem = asyncio.Semaphore(config.judge_concurrency())
        self.judge_calls = 0
        self.cache_hits = 0
        self.provider_calls = 0
        self.cost_usd = 0.0
        self._models: set[str] = set()
        self._rubrics: dict[Path, LoadedRubric] = {}
        self.metrics: dict[str, MetricDiagnostics] = {}

    @classmethod
    def create(cls, gateway: Any = None, cache: Any = None, base_dir: Path | None = None) -> JudgeContext:
        if gateway is None:
            from evalgate.llm.gateway import Gateway

            gateway = Gateway()
        return cls(gateway, cache, base_dir)

    @property
    def mode(self) -> str:
        return str(self.gateway.mode)

    def rubric(self, ref: str) -> LoadedRubric:
        path = Path(ref)
        if not path.is_file() and (self.base_dir / ref).is_file():
            path = self.base_dir / ref
        if not path.is_file():
            raise InvalidInputError(ref, "", "rubric file not found")
        key = path.resolve()
        if key not in self._rubrics:
            self._rubrics[key] = load_rubric(path)
        return self._rubrics[key]

    def diagnostics_for(self, metric: str, loaded: LoadedRubric) -> MetricDiagnostics:
        if metric not in self.metrics:
            self.metrics[metric] = MetricDiagnostics(loaded.label, loaded.prompt_version, loaded.rubric.route)
        return self.metrics[metric]

    def preflight(self, n_cases: int, metrics: list[Any]) -> None:
        """Live runs print the cost estimate first and stop (exit 3) before any call when it is over budget."""
        if not self.gateway.live:
            return
        plan = [
            (self.gateway.model_for(m.loaded.rubric.route), m.calls_per_case())
            for m in metrics
            if hasattr(m, "calls_per_case")
        ]
        estimate = estimate_judge_cost(n_cases, plan)
        print(f"evalgate: {estimate.describe()}", file=sys.stderr)
        enforce_estimate(estimate)

    def request(self, loaded: LoadedRubric, user_message: str, schema: dict[str, Any]) -> LLMRequest:
        route = loaded.rubric.route
        return LLMRequest(
            route=route,
            model=self.gateway.model_for(route),
            prompt_version=loaded.prompt_version,
            system=loaded.prompt_text,
            messages=[{"role": "user", "content": user_message}],
            schema_name=VERDICT_SCHEMA_NAME,
            schema=schema,
            effort=EFFORT[route],
            max_tokens=MAX_TOKENS,
        )

    async def verdict(self, loaded: LoadedRubric, user_message: str, schema: dict[str, Any]) -> JudgeCall:
        req = self.request(loaded, user_message, schema)
        key = request_key(req)
        self.judge_calls += 1
        if self.cache is not None:
            hit = self.cache.get(key)
            if hit is not None and not (self.gateway.live and hit.get("model") == FAKE_MODEL):
                self.cache_hits += 1
                telemetry.count("evalgate_cache_hits_total")
                model = str(hit.get("model") or req.model)
                self._models.add(model)
                return JudgeCall(JudgeVerdict.model_validate(hit["response"]), 0.0, "cache", model, True)
        async with self.sem:
            self.provider_calls += 1
            resp = await self.gateway.complete(req, validate=JudgeVerdict.model_validate)
        verdict = JudgeVerdict.model_validate(resp.data)
        self.cost_usd += resp.cost_usd
        self._models.add(resp.model)
        if self.cache is not None:
            self.cache.put(
                key,
                route=req.route,
                model=resp.model,
                prompt_version=req.prompt_version,
                request_digest=request_digest(req),
                response=verdict.model_dump(),
                input_tokens=resp.input_tokens,
                output_tokens=resp.output_tokens,
                cost_usd=resp.cost_usd,
                latency_ms=resp.latency_ms,
                replace=bool(self.gateway.live),
            )
        return JudgeCall(verdict, resp.cost_usd, resp.source, resp.model, False)

    def models_used(self) -> set[str]:
        return set(self._models)

    def prompt_hashes(self) -> dict[str, str]:
        return {r.prompt_version: r.prompt_sha256 for r in self._rubrics.values()}

    def diagnostics(self) -> dict[str, Any]:
        return {
            name: {
                "label": "AI judge",
                "rubric": d.rubric,
                "prompt_version": d.prompt_version,
                "route": d.route,
                "verdicts": dict(sorted(d.verdicts.items())),
                "position_inconsistent": d.position_inconsistent,
                "injections_blocked": d.injections_blocked,
                "errors": d.errors,
                "cases": d.cases,
            }
            for name, d in sorted(self.metrics.items())
        }
