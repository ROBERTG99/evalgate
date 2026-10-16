"""The LLM gateway: the only module that imports provider SDKs (``anthropic``, ``openai``).

It selects the provider (``EVALGATE_LLM_PROVIDER`` = fake | anthropic | bedrock | openai), redacts PII,
enforces the live budget, retries only 408, 409, 429, 5xx and connection errors (max 3 attempts, full
jitter), validates the output against the requested schema, accounts tokens and cost, and records
cassettes when ``EVALGATE_RECORD_CASSETTES=1``. There is no silent fallback to the fake provider.
"""

from __future__ import annotations

import asyncio
import json
import os
import random
import time
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, Protocol

from jsonschema import Draft202012Validator  # imported up front: a lazy import would stall the event loop

from evalgate import config, telemetry
from evalgate.accounting import has_price, step_cost
from evalgate.budget import SpendGuard
from evalgate.errors import BudgetAbortError, JudgeUnavailableError
from evalgate.llm import cassette as cassettes
from evalgate.llm.redact import redact
from evalgate.llm.types import LLMRequest, LLMResponse, OutputError, ProviderError, RawResponse

MAX_ATTEMPTS = 3
RETRIABLE_STATUS = {408, 409, 429}


class Provider(Protocol):
    name: str

    async def complete(self, req: LLMRequest) -> RawResponse: ...


def is_retriable_status(status: int | None) -> bool:
    return status is not None and (status in RETRIABLE_STATUS or status >= 500)


def _validate(data: dict[str, Any], schema: dict[str, Any]) -> None:
    errors = list(Draft202012Validator(schema).iter_errors(data))
    if errors:
        raise OutputError(f"output does not match schema: {errors[0].message}")


# providers -----------------------------------------------------------------------------------------
class AnthropicProvider:
    """Claude through the official SDK: adaptive thinking, explicit effort, structured JSON output."""

    name = "anthropic"

    def __init__(self, client: Any = None, bedrock: bool = False, timeout_s: float = 60.0) -> None:
        self.bedrock = bedrock
        if bedrock:
            self.name = "bedrock"
        self._client = client
        self.timeout_s = timeout_s

    def client(self) -> Any:
        if self._client is None:
            import anthropic

            if self.bedrock:
                region = os.environ.get("AWS_REGION", "us-east-1")
                self._client = anthropic.AsyncAnthropicBedrockMantle(
                    aws_region=region, max_retries=0, timeout=self.timeout_s
                )
            else:
                self._client = anthropic.AsyncAnthropic(max_retries=0, timeout=self.timeout_s)
        return self._client

    def model_id(self, model: str) -> str:
        return model if not self.bedrock or model.startswith("anthropic.") else f"anthropic.{model}"

    async def complete(self, req: LLMRequest) -> RawResponse:
        import anthropic

        try:
            message = await self.client().messages.create(
                model=self.model_id(req.model),
                max_tokens=req.max_tokens,
                system=[{"type": "text", "text": req.system, "cache_control": {"type": "ephemeral"}}],
                messages=req.messages,
                thinking={"type": "adaptive"},
                # Structured outputs reject numeric and array constraints; the SDK moves them into
                # descriptions and the gateway still validates the full schema client-side.
                output_config={
                    "effort": req.effort,
                    "format": {"type": "json_schema", "schema": anthropic.transform_schema(req.schema)},
                },
            )
        except anthropic.APIStatusError as exc:  # most specific first: status errors carry the code
            raise ProviderError(
                f"anthropic {exc.status_code}: {exc.message}", is_retriable_status(exc.status_code), exc.status_code
            ) from exc
        except anthropic.APITimeoutError as exc:
            raise ProviderError("anthropic timeout", True) from exc
        except anthropic.APIConnectionError as exc:
            raise ProviderError("anthropic connection error", True) from exc
        if message.stop_reason == "refusal":
            raise OutputError("model refused")
        if message.stop_reason == "max_tokens":
            raise OutputError("max_tokens reached before the verdict was complete")
        text = next((b.text for b in message.content if b.type == "text"), "")
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise OutputError(f"invalid JSON from model: {exc}") from exc
        return RawResponse(
            data=data,
            input_tokens=message.usage.input_tokens,
            output_tokens=message.usage.output_tokens,
            stop_reason=str(message.stop_reason),
            model=req.model,
        )


class OpenAIProvider:
    """OpenAI chat completions with a strict JSON schema response format."""

    name = "openai"

    def __init__(self, client: Any = None, timeout_s: float = 60.0) -> None:
        self._client = client
        self.timeout_s = timeout_s

    def client(self) -> Any:
        if self._client is None:
            import openai

            self._client = openai.AsyncOpenAI(max_retries=0, timeout=self.timeout_s)
        return self._client

    async def complete(self, req: LLMRequest) -> RawResponse:
        import openai

        try:
            completion = await self.client().chat.completions.create(
                model=req.model,
                max_completion_tokens=req.max_tokens,
                messages=[{"role": "system", "content": req.system}, *req.messages],
                response_format={
                    "type": "json_schema",
                    "json_schema": {"name": req.schema_name.replace(".", "_"), "schema": req.schema, "strict": True},
                },
            )
        except openai.APIStatusError as exc:
            raise ProviderError(
                f"openai {exc.status_code}", is_retriable_status(exc.status_code), exc.status_code
            ) from exc
        except openai.APITimeoutError as exc:
            raise ProviderError("openai timeout", True) from exc
        except openai.APIConnectionError as exc:
            raise ProviderError("openai connection error", True) from exc
        choice = completion.choices[0]
        if getattr(choice.message, "refusal", None):
            raise OutputError("model refused")
        if choice.finish_reason == "length":
            raise OutputError("max tokens reached before the verdict was complete")
        try:
            data = json.loads(choice.message.content or "")
        except json.JSONDecodeError as exc:
            raise OutputError(f"invalid JSON from model: {exc}") from exc
        usage = completion.usage
        return RawResponse(
            data=data,
            input_tokens=usage.prompt_tokens if usage else 0,
            output_tokens=usage.completion_tokens if usage else 0,
            stop_reason=str(choice.finish_reason),
            model=req.model,
        )


def build_provider(name: str, timeout_s: float, cassette_dir: Path | None = None) -> Provider:
    if name == "fake":
        from evalgate.llm.fake import FakeLLM

        return FakeLLM(cassette_dir)
    if name == "anthropic":
        return AnthropicProvider(timeout_s=timeout_s)
    if name == "bedrock":
        return AnthropicProvider(bedrock=True, timeout_s=timeout_s)
    if name == "openai":
        return OpenAIProvider(timeout_s=timeout_s)
    raise ValueError(f"unknown EVALGATE_LLM_PROVIDER {name!r}; use fake, anthropic, bedrock or openai")


# gateway ---------------------------------------------------------------------------------------------
class Gateway:
    def __init__(
        self,
        provider: Provider | None = None,
        provider_name: str | None = None,
        *,
        cassette_dir: Path | None = None,
        record: bool | None = None,
        budget_usd: float | None = None,
        timeout_s: float | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        rng: random.Random | None = None,
    ) -> None:
        name = provider_name or (provider.name if provider is not None else config.llm_provider())
        self.timeout_s = timeout_s or config.judge_timeout_s()
        self.cassette_dir = cassette_dir if cassette_dir is not None else cassettes.default_dir()
        self.provider: Provider = provider or build_provider(name, self.timeout_s, self.cassette_dir)
        self.provider_name = name
        self.live = name != "fake"
        self.record = (os.environ.get("EVALGATE_RECORD_CASSETTES") == "1") if record is None else record
        self.guard = SpendGuard(
            budget_usd if budget_usd is not None else (config.live_budget_usd() if self.live else None)
        )
        self.sleep = sleep
        self.rng = rng or random.Random()  # noqa: S311 - jitter only
        self.calls = 0

    @property
    def mode(self) -> str:
        return "live" if self.live else "offline"

    def model_for(self, route: str) -> str:
        return config.judge_hard_model() if route == "judge_hard" else config.judge_model()

    def _cost(self, model: str, raw: RawResponse) -> float:
        return step_cost(model, raw.input_tokens, raw.output_tokens) if self.live else 0.0

    async def complete(self, req: LLMRequest, validate: Callable[[dict[str, Any]], Any] | None = None) -> LLMResponse:
        """Send one request. Raises JudgeUnavailable when retriable failures persist after 3 attempts,
        OutputError when the output is unusable, BudgetAbortError when the live budget is spent."""
        req = LLMRequest(
            route=req.route,
            model=req.model,
            prompt_version=req.prompt_version,
            system=req.system,
            messages=[{"role": m["role"], "content": redact(m["content"])} for m in req.messages],
            schema_name=req.schema_name,
            schema=req.schema,
            effort=req.effort,
            max_tokens=req.max_tokens,
        )
        if self.live:
            if not has_price(req.model):
                raise BudgetAbortError(
                    f"model {req.model!r} has no price in pricing.yaml, so LIVE_EVAL_BUDGET_USD cannot be enforced"
                )
            self.guard.check()
        last: Exception | None = None
        for attempt in range(1, MAX_ATTEMPTS + 1):
            start = time.perf_counter()
            try:
                with telemetry.span(
                    "evalgate.judge",
                    gen_ai__request__model=req.model,
                    app__prompt_version=req.prompt_version,
                    gen_ai__operation__name="chat",
                    app__route=req.route,
                ) as current:
                    self.calls += 1
                    raw = await asyncio.wait_for(self.provider.complete(req), timeout=self.timeout_s)
                    if current is not None:
                        current.set_attribute("gen_ai.response.model", raw.model or req.model)
                        current.set_attribute("gen_ai.usage.input_tokens", raw.input_tokens)
                        current.set_attribute("gen_ai.usage.output_tokens", raw.output_tokens)
                        current.set_attribute("app.cost_usd", self._cost(raw.model or req.model, raw))
            except TimeoutError as exc:
                last = ProviderError("provider timeout", True)
                last.__cause__ = exc
            except ProviderError as exc:
                if not exc.retriable:
                    raise JudgeUnavailableError(f"{self.provider_name}: {exc}") from exc
                last = exc
            else:
                latency = (time.perf_counter() - start) * 1000
                model = raw.model or req.model
                cost = self._cost(model, raw)
                self.guard.add(cost)  # paid even if the output turns out unusable
                try:
                    _validate(raw.data, req.schema)
                    if validate is not None:
                        try:
                            validate(raw.data)
                        except ValueError as exc:  # pydantic ValidationError is a ValueError
                            raise OutputError(f"output does not match the contract: {exc}".splitlines()[0]) from exc
                except OutputError as exc:
                    exc.cost_usd = cost
                    raise
                if self.live and self.record:
                    cassettes.save(self.cassette_dir, req, raw.data, raw.input_tokens, raw.output_tokens)
                return LLMResponse(
                    data=raw.data,
                    input_tokens=raw.input_tokens,
                    output_tokens=raw.output_tokens,
                    cost_usd=cost,
                    latency_ms=latency,
                    model=model,
                    provider=self.provider_name,
                    source=raw.source,
                    attempts=attempt,
                )
            if attempt < MAX_ATTEMPTS:
                await self.sleep(self.rng.uniform(0, min(8.0, 0.5 * 2 ** (attempt - 1))))
        raise JudgeUnavailableError(f"{self.provider_name}: {last} after {MAX_ATTEMPTS} attempts")
