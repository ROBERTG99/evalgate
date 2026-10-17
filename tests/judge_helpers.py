"""Helpers for judge tests: scripted providers and a judge context without a cache."""

from __future__ import annotations

from typing import Any

from evalgate.judge.context import JudgeContext
from evalgate.llm.gateway import Gateway
from evalgate.llm.types import LLMRequest, RawResponse

RUBRICS = "evals/rubrics"


class Scripted:
    name = "scripted"

    def __init__(self, verdicts: list[dict[str, Any]] | None = None, always: dict[str, Any] | None = None) -> None:
        self.verdicts = verdicts or []
        self.always = always
        self.calls = 0
        self.requests: list[LLMRequest] = []

    async def complete(self, req: LLMRequest) -> RawResponse:
        self.calls += 1
        self.requests.append(req)
        data = self.always if self.always is not None else self.verdicts.pop(0)
        return RawResponse(data=data, input_tokens=500, output_tokens=40, model=req.model)


async def _no_sleep(_: float) -> None:
    return None


def context(provider: Any = None, live: bool = False, cache: Any = None) -> JudgeContext:
    if provider is None:
        gw = Gateway(provider_name="fake")
    else:
        gw = Gateway(provider, provider_name="anthropic" if live else "fake", budget_usd=5.0, sleep=_no_sleep)
    return JudgeContext(gw, cache)


def verdict(v: str, score: float = 1.0, criteria: dict[str, str] | None = None) -> dict[str, Any]:
    return {"verdict": v, "score": score, "reasons": ["scripted"], "criteria": criteria or {}}
