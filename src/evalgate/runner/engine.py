"""The runner: cases under a semaphore, timeouts and retries, metrics, pricing, report and store."""

from __future__ import annotations

import asyncio
import importlib
import logging
import random
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from evalgate import config, telemetry
from evalgate.accounting import price_steps, step_cost
from evalgate.contracts import Case, MetricScore, Report, StepRecord, TargetResult
from evalgate.errors import EvalgateError, InvalidInputError
from evalgate.ids import canonical_json, sha256_text, uuid7
from evalgate.metrics.registry import build_metric
from evalgate.report.build import CaseOutcome, build_report
from evalgate.runner.retry import CaseFailure, call_with_retries
from evalgate.suite.loader import LoadedSuite
from evalgate.targets import Target, build_target

log = logging.getLogger("evalgate.runner")
CacheMode = Literal["rw", "ro", "off"]
DEGRADED_ERROR_RATE = 0.5


@dataclass
class RunOptions:
    split: str | None = None
    cache_mode: CacheMode = "rw"
    cache_targets: bool = False
    resume: str | None = None
    otel: bool = False
    use_store: bool = True
    home: Path | None = None
    seed: int | None = None
    resamples: int = 10_000
    case_timeout_s: float | None = None
    run_timeout_s: float | None = None
    retries: int | None = None
    target: Target | None = None
    gateway: Any = None
    http_client: Any = None
    rng_seed: int | None = None
    extra_extensions: dict[str, Any] = field(default_factory=dict)


@dataclass
class RunResult:
    report: Report
    outcomes: list[CaseOutcome]
    store_error: str | None = None


def ensure_import_paths(suite_path: Path) -> None:
    """``python:`` targets and plugins resolve against the working directory, then the suite's folder."""
    for entry in (str(Path.cwd()), str(suite_path.resolve().parent)):
        if entry not in sys.path:
            sys.path.append(entry)


def _import_plugins(modules: list[str], suite_path: Path) -> None:
    ensure_import_paths(suite_path)
    for module in modules:
        try:
            importlib.import_module(module)
        except ImportError as exc:
            raise InvalidInputError(str(suite_path), "$.plugins", f"cannot import {module!r}: {exc}") from exc


def _target_cache_key(suite_name: str, target_desc: str, case_input: dict[str, Any]) -> str:
    return sha256_text(f"target|{suite_name}|{target_desc}|{canonical_json(case_input)}")


class Runner:
    def __init__(self, loaded: LoadedSuite, options: RunOptions) -> None:
        self.loaded = loaded
        self.suite = loaded.suite
        self.options = options
        self.home = options.home or config.home()
        self.seed = config.bootstrap_seed() if options.seed is None else options.seed
        self.case_timeout = options.case_timeout_s or config.case_timeout_s()
        self.run_timeout = options.run_timeout_s or config.run_timeout_s()
        self.retries = config.target_retries() if options.retries is None else options.retries
        self.rng = random.Random(options.rng_seed)  # noqa: S311 - jitter only
        self.cache: Any = None
        self.store: Any = None
        self.store_error: str | None = None
        self.judge_ctx: Any = None
        self.run_id = options.resume or uuid7()
        self._owned_client: Any = None

    # setup -----------------------------------------------------------------------------------
    def _needs_judge(self) -> bool:
        return any(m.kind == "judge" for m in self.suite.metrics)

    def _open_cache(self) -> None:
        if self.options.cache_mode == "off" or not (self._needs_judge() or self.options.cache_targets):
            return
        from evalgate.cache import ResponseCache

        self.cache = ResponseCache(self.home / "cache.duckdb", mode=self.options.cache_mode)

    def _open_store(self) -> None:
        if not self.options.use_store:
            return
        try:
            from evalgate.store import RunStore

            self.store = RunStore(self.home / "runs.duckdb")
        except Exception as exc:  # run store down -> the report is still written
            self.store_error = f"{exc.__class__.__name__}: {exc}"
            log.warning("run store unavailable, continuing without it: %s", self.store_error)
            self.store = None

    def _build_metrics(self) -> list[Any]:
        metrics = []
        judge_kwargs: dict[str, Any] = {}
        if self._needs_judge():
            from evalgate.judge.context import JudgeContext

            self.judge_ctx = JudgeContext.create(
                gateway=self.options.gateway, cache=self.cache, base_dir=self.loaded.path.parent
            )
            judge_kwargs["ctx"] = self.judge_ctx
        for spec in self.suite.metrics:
            try:
                metrics.append(build_metric(spec, **judge_kwargs) if spec.kind == "judge" else build_metric(spec))
            except (KeyError, FileNotFoundError, ValueError) as exc:
                idx = self.suite.metrics.index(spec)
                raise InvalidInputError(str(self.loaded.path), f"$.metrics[{idx}]", str(exc)) from exc
        return metrics

    # per case --------------------------------------------------------------------------------
    async def _call_target(self, target: Target, case: Case) -> tuple[TargetResult, int, float]:
        key = None
        if self.options.cache_targets and self.cache is not None:
            key = _target_cache_key(self.suite.name, self.suite.target.model_dump_json(), case.input)
            hit = self.cache.get(key)
            if hit is not None:
                return TargetResult.model_validate(hit["response"]), 0, float(hit.get("latency_ms") or 0.0)
        start = time.perf_counter()
        result, attempts = await call_with_retries(
            target, case.input, retries=self.retries, timeout_s=self.case_timeout, rng=self.rng
        )
        latency = (time.perf_counter() - start) * 1000
        if key is not None and self.cache is not None:
            self.cache.put(
                key,
                route="target",
                model=None,
                prompt_version=None,
                request_digest=key,
                response=result.model_dump(mode="json"),
                cost_usd=result.cost_usd,
                latency_ms=latency,
            )
        return result, attempts, latency

    async def _score(self, metrics: list[Any], case: Case, result: TargetResult) -> list[MetricScore]:
        scores: list[MetricScore] = []
        for metric in metrics:
            with telemetry.span("evalgate.metric", app__run_id=self.run_id, app__case_id=case.id, metric=metric.name):
                try:
                    if hasattr(metric, "ascore"):
                        score = await metric.ascore(case, result)
                    else:
                        score = metric.score(case, result)
                except EvalgateError as exc:
                    if exc.exit_code == 3:
                        raise
                    score = MetricScore(
                        name=metric.name,
                        value=0.0,
                        passed=False,
                        details={"error": str(exc)[:300], "metric_error": True},
                    )
                except Exception as exc:
                    score = MetricScore(
                        name=metric.name,
                        value=0.0,
                        passed=False,
                        details={"error": f"{exc.__class__.__name__}: {exc}"[:300], "metric_error": True},
                    )
            scores.append(score)
        return scores

    async def run_case(self, target: Target, metrics: list[Any], case: Case, sem: asyncio.Semaphore) -> CaseOutcome:
        async with sem:
            with telemetry.span("evalgate.case", app__run_id=self.run_id, app__case_id=case.id):
                started = time.perf_counter()
                try:
                    with telemetry.span("evalgate.target", app__run_id=self.run_id, app__case_id=case.id):
                        result, attempts, latency = await self._call_target(target, case)
                except CaseFailure as failure:
                    scores = [MetricScore(name=m.name, value=0.0, passed=False, details={}) for m in metrics]
                    telemetry.count("evalgate_case_errors_total")
                    return CaseOutcome(
                        case_id=case.id,
                        split=case.split,
                        scores=scores,
                        passed=False,
                        cost_usd=0.0,
                        latency_ms=(time.perf_counter() - started) * 1000,
                        attempts=failure.attempts,
                        error=failure.error,
                        tags=case.tags,
                    )
                steps = price_steps(result.steps)
                for i, step in enumerate(steps):
                    steps[i] = step.model_copy(update={"run_id": self.run_id, "task_id": case.id, "step": i})
                    with telemetry.span(
                        "evalgate.step",
                        app__run_id=self.run_id,
                        app__node=step.node,
                        app__cost_usd=step.cost_usd,
                        app__prompt_version=step.prompt_version,
                        gen_ai__request__model=step.model,
                        gen_ai__usage__input_tokens=step.input_tokens,
                        gen_ai__usage__output_tokens=step.output_tokens,
                    ):
                        pass
                    if step.model:
                        telemetry.count(
                            "evalgate_tokens_total", step.input_tokens + step.output_tokens, model=step.model
                        )
                target_cost = result.cost_usd or sum(s.cost_usd for s in steps)
                scores = await self._score(metrics, case, result)
                judge_cost = sum(float(s.details.get("cost_usd", 0.0)) for s in scores)
                gated = {m.name for m in self.suite.metrics if m.gate}
                passed = all(s.passed for s in scores if s.name in gated)
                telemetry.count("evalgate_case_latency_ms", latency, suite=self.suite.name)
                telemetry.count("evalgate_cost_usd_total", target_cost + judge_cost)
                return CaseOutcome(
                    case_id=case.id,
                    split=case.split,
                    scores=scores,
                    passed=passed,
                    cost_usd=target_cost + judge_cost,
                    latency_ms=latency,
                    attempts=attempts,
                    error=None,
                    steps=steps,
                    tags=case.tags,
                )

    # whole run -------------------------------------------------------------------------------
    async def _writer(self, queue: asyncio.Queue[CaseOutcome | None]) -> None:
        while True:
            item = await queue.get()
            if item is None:
                return
            if self.store is not None:
                try:
                    # DuckDB writes are blocking: keep them off the event loop so latencies stay honest.
                    await asyncio.to_thread(self.store.insert_case, self.run_id, item)
                except Exception as exc:
                    self.store_error = f"{exc.__class__.__name__}: {exc}"
                    log.warning("run store write failed: %s", self.store_error)
                    self.store = None

    async def run(self) -> RunResult:
        _import_plugins(self.suite.plugins, self.loaded.path)
        self._open_cache()
        self._open_store()
        try:
            metrics = self._build_metrics()
            http_client = self.options.http_client
            if http_client is None and self.suite.target.http is not None and self.options.target is None:
                import httpx

                # One pooled client per run: building a client (and its TLS context) per call costs ~100 ms.
                limits = httpx.Limits(max_connections=self.suite.concurrency * 2)
                http_client = self._owned_client = httpx.AsyncClient(limits=limits)
            target = self.options.target or build_target(self.suite.target, http_client=http_client)
            cases = self.loaded.cases
            if self.judge_ctx is not None:
                self.judge_ctx.preflight(n_cases=len(cases), metrics=metrics)
            done: dict[str, CaseOutcome] = {}
            if self.options.resume and self.store is not None:
                done = {o.case_id: o for o in self.store.get_cases(self.run_id)}
            pending = [c for c in cases if c.id not in done]
            sem = asyncio.Semaphore(self.suite.concurrency)
            queue: asyncio.Queue[CaseOutcome | None] = asyncio.Queue(maxsize=1000)
            writer = asyncio.create_task(self._writer(queue))
            outcomes: list[CaseOutcome] = list(done.values())
            with telemetry.span("evalgate.run", app__run_id=self.run_id, suite=self.suite.name):
                tasks = [asyncio.create_task(self.run_case(target, metrics, c, sem)) for c in pending]
                try:
                    finished, unfinished = (
                        await asyncio.wait(tasks, timeout=self.run_timeout) if tasks else (set(), set())
                    )
                    for task in unfinished:
                        task.cancel()
                    for case, task in zip(pending, tasks, strict=True):
                        if task in finished:
                            outcome = task.result()
                        else:
                            outcome = CaseOutcome(
                                case_id=case.id,
                                split=case.split,
                                scores=[MetricScore(name=m.name, value=0.0, passed=False) for m in metrics],
                                passed=False,
                                cost_usd=0.0,
                                latency_ms=0.0,
                                attempts=0,
                                error="run_timeout",
                            )
                        outcomes.append(outcome)
                        await queue.put(outcome)
                finally:
                    await queue.put(None)
                    await writer
            report = self._report(outcomes)
            if self.store is not None:
                try:
                    self.store.finish_run(report)
                except Exception as exc:
                    self.store_error = f"{exc.__class__.__name__}: {exc}"
                    log.warning("run store finish failed: %s", self.store_error)
            return RunResult(report=report, outcomes=outcomes, store_error=self.store_error)
        finally:
            if self._owned_client is not None:
                await self._owned_client.aclose()
            if self.store is not None:
                self.store.close()
            if self.cache is not None:
                self.cache.close()

    def _report(self, outcomes: list[CaseOutcome]) -> Report:
        n = len(outcomes)
        errors = sum(1 for o in outcomes if o.error)
        error_rate = errors / n if n else 0.0
        models: set[str] = {s.model for o in outcomes for s in o.steps if isinstance(s, StepRecord) and s.model}
        prompt_hashes: dict[str, str] = {}
        metric_errors = {
            m.name: sum(
                1
                for o in outcomes
                if not o.error
                for s in o.scores
                if s.name == m.name and s.details.get("metric_error")
            )
            for m in self.suite.metrics
        }
        ext: dict[str, Any] = {
            "run_health": "degraded" if error_rate > DEGRADED_ERROR_RATE else "ok",
            "error_rate": round(error_rate, 6),
            "attempts": {o.case_id: o.attempts for o in sorted(outcomes, key=lambda o: o.case_id) if o.attempts != 1},
            "gates": {m.name: m.gate for m in self.suite.metrics},
            "metric_errors": {k: v for k, v in metric_errors.items() if v},
            "budget": self.suite.budget.model_dump() if self.suite.budget else None,
            "split": self.options.split,
            "seed": self.seed,
            "resamples": self.options.resamples,
            "unpriced_models": sorted(
                {
                    s.model
                    for o in outcomes
                    for s in o.steps
                    if s.model
                    and step_cost(s.model, 1_000_000, 0) == 0
                    and s.model != "fake-judge"
                    and (s.input_tokens or s.output_tokens)
                }
            ),
        }
        mode = "offline"
        if self.judge_ctx is not None:
            mode = self.judge_ctx.mode
            models |= self.judge_ctx.models_used()
            prompt_hashes.update(self.judge_ctx.prompt_hashes())
            ext["cache_hits"] = self.judge_ctx.cache_hits
            ext["judge_calls"] = self.judge_ctx.judge_calls
            ext["provider_calls"] = self.judge_ctx.provider_calls
            ext["judge"] = self.judge_ctx.diagnostics()
            ext["judge_cost_usd"] = round(self.judge_ctx.cost_usd, 10)
        judged = {m.name for m in self.suite.metrics if m.kind == "judge"}
        if judged:
            ext["judge_details"] = {
                o.case_id: {s.name: s.details for s in o.scores if s.name in judged and s.details}
                for o in sorted(outcomes, key=lambda o: o.case_id)
            }
        tags = {o.case_id: o.tags for o in sorted(outcomes, key=lambda o: o.case_id) if o.tags}
        if tags:
            ext["case_tags"] = tags
        if self.store_error:
            ext["store_error"] = self.store_error
        ext.update(self.options.extra_extensions)
        return build_report(
            self.suite,
            outcomes,
            run_id=self.run_id,
            mode=mode,
            models=sorted(models),
            prompt_hashes=prompt_hashes,
            seed=self.seed,
            resamples=self.options.resamples,
            extensions=ext,
        )


async def run_suite_async(loaded: LoadedSuite, options: RunOptions | None = None) -> RunResult:
    options = options or RunOptions()
    if options.otel:
        telemetry.setup(enabled=True)
    try:
        return await Runner(loaded, options).run()
    finally:
        if options.otel:
            telemetry.shutdown()


def run_suite(loaded: LoadedSuite, options: RunOptions | None = None) -> RunResult:
    return asyncio.run(run_suite_async(loaded, options))
