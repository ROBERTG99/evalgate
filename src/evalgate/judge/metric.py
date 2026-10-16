"""``kind: judge`` metrics: an LLM judge with position swap, candidate isolation and an injection guard."""

from __future__ import annotations

from typing import Any

from evalgate.contracts import Case, MetricScore, MetricSpec, TargetResult
from evalgate.errors import EvalgateError
from evalgate.judge.context import JudgeCall, JudgeContext
from evalgate.judge.guard import injection_match
from evalgate.judge.render import render_user, verdict_schema
from evalgate.llm.types import OutputError
from evalgate.metrics.base import BaseMetric, context
from evalgate.suite.selectors import resolve

MIRROR = {"A": "B", "B": "A", "tie": "tie"}


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    import json

    return json.dumps(value, ensure_ascii=False, sort_keys=True)


class JudgeMetric(BaseMetric):
    """Params: ``rubric`` (path), ``candidate`` (default ``output.answer``), ``reference``
    (default ``expected.answer``), ``input`` (default ``input``) and, for pairwise rubrics, ``candidate_b``."""

    def __init__(self, spec: MetricSpec, ctx: JudgeContext) -> None:
        super().__init__(spec)
        self.ctx = ctx
        self.loaded = ctx.rubric(str(self.params["rubric"]))
        self.rubric = self.loaded.rubric
        self.schema = verdict_schema(self.rubric)
        if "pass_at" not in self.params:
            self.pass_at = 0.75 if self.rubric.scale == "likert5" else 1.0
        self.diag = ctx.diagnostics_for(spec.name, self.loaded)
        injection_match("")  # load and compile the patterns before the run starts

    def calls_per_case(self) -> int:
        return 2 if self.rubric.position_swap else 1

    def score(self, case: Case, result: TargetResult) -> MetricScore:  # pragma: no cover - async only
        raise RuntimeError("judge metrics are async; the runner calls ascore()")

    def _value(self, verdict: str, score: float) -> float:
        if self.rubric.mode == "pairwise":
            return {"A": 1.0, "B": 0.0, "tie": 0.5}[verdict]
        if self.rubric.scale == "likert5":
            return score
        return 1.0 if verdict == "pass" else 0.0

    async def ascore(self, case: Case, result: TargetResult) -> MetricScore:
        ctx = context(case, result)
        candidate = _text(resolve(self.params.get("candidate", "output.answer"), ctx))
        reference = _text(resolve(self.params.get("reference", "expected.answer"), ctx))
        task_input = _text(resolve(self.params.get("input", "input"), ctx))
        candidate_b = _text(resolve(self.params.get("candidate_b", "expected.answer"), ctx))
        return await self.judge(task_input, reference, candidate, candidate_b)

    async def judge(self, task_input: str, reference: str, candidate: str, candidate_b: str = "") -> MetricScore:
        self.diag.cases += 1
        base = {"label": "AI judge", "rubric": self.loaded.label, "prompt_version": self.loaded.prompt_version}
        hit = injection_match(candidate)
        if hit:
            self.diag.injections_blocked += 1
            self.diag.verdicts["injection"] = self.diag.verdicts.get("injection", 0) + 1
            return self.make(0.0, **base, verdict="fail", injection=hit, reasons=["instruction aimed at the grader"])
        orders = ["AB", "BA"] if self.rubric.mode == "pairwise" else ["reference_first", "candidate_first"]
        if not self.rubric.position_swap:
            orders = orders[:1]
        calls: list[JudgeCall] = []
        try:
            for order in orders:
                message = render_user(
                    self.rubric,
                    task_input=task_input,
                    reference=reference,
                    candidate=candidate,
                    candidate_b=candidate_b,
                    order=order,
                )
                calls.append(await self.ctx.verdict(self.loaded, message, self.schema))
        except OutputError as exc:
            self.diag.errors += 1
            spent = sum(c.cost_usd for c in calls) + exc.cost_usd  # failed calls still cost money
            return self.make(0.0, **base, error=f"invalid judge output: {exc}"[:300], metric_error=True, cost_usd=spent)
        except EvalgateError as exc:
            if exc.exit_code == 3:
                raise
            self.diag.errors += 1
            spent = sum(c.cost_usd for c in calls)
            return self.make(0.0, **base, error=str(exc)[:300], metric_error=True, cost_usd=spent)
        verdicts: list[str] = [c.verdict.verdict for c in calls]
        if self.rubric.mode == "pairwise" and len(verdicts) == 2:
            verdicts[1] = MIRROR[verdicts[1]]
        cost = sum(c.cost_usd for c in calls)
        first = calls[0].verdict
        details: dict[str, Any] = {
            **base,
            "verdict": first.verdict,
            "reasons": first.reasons,
            "criteria": first.criteria,
            "model": calls[0].model,
            "source": calls[0].source,
            "cost_usd": cost,
            "calls": len(calls),
        }
        if len(set(verdicts)) > 1:
            self.diag.position_inconsistent += 1
            self.diag.verdicts["position_inconsistent"] = self.diag.verdicts.get("position_inconsistent", 0) + 1
            return self.make(0.5, **details, position_inconsistent=True, verdicts=verdicts)
        self.diag.verdicts[first.verdict] = self.diag.verdicts.get(first.verdict, 0) + 1
        scores = [c.verdict.score for c in calls]
        value = self._value(verdicts[0], sum(scores) / len(scores))
        return self.make(value, **details)
