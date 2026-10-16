import asyncio
import json
from pathlib import Path
from typing import Any

import pytest

from evalgate.errors import CassetteMismatch, JudgeUnavailableError
from evalgate.llm.cassette import request_digest, save
from evalgate.llm.fake import FakeLLM
from evalgate.llm.gateway import AnthropicProvider, Gateway, OpenAIProvider
from evalgate.llm.redact import luhn_ok, redact
from evalgate.llm.types import LLMRequest, OutputError, ProviderError, RawResponse

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "provider_responses"
SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": ["pass", "fail"]},
        "score": {"type": "number"},
        "reasons": {"type": "array", "items": {"type": "string"}},
        "criteria": {"type": "object"},
    },
    "required": ["verdict", "score", "reasons", "criteria"],
}
USER = (
    '<rubric name="answer_correctness" version="1" mode="pointwise" scale="binary">\n<criteria>\n'
    "- states_key_facts\n</criteria>\n</rubric>\n<task_input>How long?</task_input>\n"
    "<reference>Returns within 30 days.</reference>\n<candidate_output>Within 30 days.</candidate_output>"
)


def test_unpriced_live_model_refused() -> None:
    from evalgate.errors import BudgetAbortError

    provider = Scripted([VERDICT])
    gw = Gateway(provider, provider_name="openai", budget_usd=1.0, sleep=no_sleep)
    with pytest.raises(BudgetAbortError, match="no price"):
        asyncio.run(gw.complete(request(model="gpt-unpriced")))
    assert provider.calls == 0


def test_sdk_errors_classified() -> None:
    import anthropic
    import httpx2

    def status_error(code: int) -> Exception:
        req = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
        return anthropic.APIStatusError("err", response=httpx2.Response(code, request=req), body=None)

    def raising(exc: Exception) -> Any:
        async def create(**kwargs: Any) -> Any:
            raise exc

        return type("C", (), {"messages": _Obj(create)})()

    for code, retriable in [
        (408, True),
        (409, True),
        (429, True),
        (500, True),
        (529, True),
        (400, False),
        (401, False),
    ]:
        with pytest.raises(ProviderError) as info:
            asyncio.run(AnthropicProvider(client=raising(status_error(code))).complete(request()))
        assert info.value.retriable is retriable, code
    conn = anthropic.APIConnectionError(request=httpx2.Request("POST", "https://api.anthropic.com/v1/messages"))
    with pytest.raises(ProviderError) as info:
        asyncio.run(AnthropicProvider(client=raising(conn)).complete(request()))
    assert info.value.retriable


def request(**kw: Any) -> LLMRequest:
    base = dict(
        route="judge",
        model="claude-haiku-5-5",
        prompt_version="judge_answer_correctness.v1",
        system="You are a strict grader.",
        messages=[{"role": "user", "content": USER}],
        schema_name="judge_verdict.v1",
        schema=SCHEMA,
        effort="low",
        max_tokens=1024,
    )
    base.update(kw)
    return LLMRequest(**base)


async def no_sleep(_: float) -> None:
    return None


class Scripted:
    name = "scripted"

    def __init__(self, outcomes: list[Any]) -> None:
        self.outcomes = outcomes
        self.calls = 0
        self.seen: list[LLMRequest] = []

    async def complete(self, req: LLMRequest) -> RawResponse:
        self.calls += 1
        self.seen.append(req)
        item = self.outcomes.pop(0)
        if isinstance(item, Exception):
            raise item
        return RawResponse(data=item, input_tokens=100, output_tokens=10, model=req.model)


VERDICT = {"verdict": "pass", "score": 1.0, "reasons": [], "criteria": {}}


def test_digest_mismatch(tmp_path: Path) -> None:
    req = request()
    save(tmp_path, req, VERDICT, 10, 5)
    fake = FakeLLM(tmp_path)
    replay = asyncio.run(fake.complete(req))
    assert replay.source == "cassette"
    changed = request(effort="high")  # same key (route, model, prompt version, messages), different digest
    assert request_digest(changed) != request_digest(req)
    with pytest.raises(CassetteMismatch):
        asyncio.run(fake.complete(changed))


def test_fake_llm_without_cassette_uses_rules(tmp_path: Path) -> None:
    out = asyncio.run(FakeLLM(tmp_path).complete(request()))
    assert out.source == "rules"
    assert out.data["verdict"] == "pass"


def test_pii_redacted() -> None:
    text = (
        "Mail jane.doe@example.com or call +44 20 7946 0958; card 4111 1111 1111 1111; "
        "order 1234567890123 is not a card; refund within 30 days."
    )
    out = redact(text)
    assert "[EMAIL]" in out and "jane.doe" not in out
    assert "[PHONE]" in out and "7946" not in out
    assert "[CARD]" in out and "4111" not in out
    assert "30 days" in out
    assert luhn_ok("4111111111111111") and not luhn_ok("4111111111111112")
    provider = Scripted([VERDICT])
    gw = Gateway(provider, provider_name="anthropic", budget_usd=1.0, sleep=no_sleep)
    asyncio.run(gw.complete(request(messages=[{"role": "user", "content": USER + " jane.doe@example.com"}])))
    assert "jane.doe@example.com" not in provider.seen[0].messages[0]["content"]


def test_only_retriable_retried() -> None:
    retriable = Scripted([ProviderError("429", True, 429), ProviderError("503", True, 503), VERDICT])
    gw = Gateway(retriable, provider_name="anthropic", budget_usd=1.0, sleep=no_sleep)
    resp = asyncio.run(gw.complete(request()))
    assert resp.attempts == 3
    assert retriable.calls == 3
    assert resp.cost_usd > 0

    exhausted = Scripted([ProviderError("500", True, 500)] * 3)
    with pytest.raises(JudgeUnavailableError, match="after 3 attempts"):
        asyncio.run(Gateway(exhausted, provider_name="anthropic", budget_usd=1.0, sleep=no_sleep).complete(request()))
    assert exhausted.calls == 3

    bad_request = Scripted([ProviderError("400", False, 400), VERDICT])
    with pytest.raises(JudgeUnavailableError):
        asyncio.run(Gateway(bad_request, provider_name="anthropic", budget_usd=1.0, sleep=no_sleep).complete(request()))
    assert bad_request.calls == 1


def test_invalid_output_is_error_never_pass() -> None:
    gw = Gateway(
        Scripted([{"verdict": "maybe", "score": 1, "reasons": [], "criteria": {}}]),
        provider_name="anthropic",
        budget_usd=1.0,
        sleep=no_sleep,
    )
    with pytest.raises(OutputError):
        asyncio.run(gw.complete(request()))


def test_live_budget_hard_stop() -> None:
    from evalgate.errors import BudgetAbortError

    gw = Gateway(Scripted([VERDICT, VERDICT]), provider_name="anthropic", budget_usd=0.00001, sleep=no_sleep)
    asyncio.run(gw.complete(request()))
    with pytest.raises(BudgetAbortError):
        asyncio.run(gw.complete(request()))


def test_records_cassettes_in_live_mode(tmp_path: Path) -> None:
    gw = Gateway(
        Scripted([VERDICT]),
        provider_name="anthropic",
        budget_usd=1.0,
        sleep=no_sleep,
        cassette_dir=tmp_path,
        record=True,
    )
    asyncio.run(gw.complete(request()))
    files = list((tmp_path / "judge").glob("*.json"))
    assert len(files) == 1
    replay = asyncio.run(FakeLLM(tmp_path).complete(request()))
    assert replay.source == "cassette"
    assert replay.data == VERDICT


class _Obj:
    def __init__(self, fn: Any) -> None:
        self.create = fn


def test_anthropic_adapter_against_recorded_response() -> None:
    from anthropic.types import Message

    payload = json.loads((FIXTURES / "anthropic_message.json").read_text())
    payload.pop("_note")
    captured: dict[str, Any] = {}

    async def create(**kwargs: Any) -> Message:
        captured.update(kwargs)
        return Message.model_validate(payload)

    client = type("C", (), {"messages": _Obj(create)})()
    raw = asyncio.run(AnthropicProvider(client=client).complete(request()))
    assert raw.data["verdict"] == "pass"
    assert (raw.input_tokens, raw.output_tokens) == (612, 48)
    assert captured["thinking"] == {"type": "adaptive"}
    assert captured["output_config"]["effort"] == "low"
    assert captured["output_config"]["format"]["type"] == "json_schema"
    sent = json.dumps(captured["output_config"]["format"]["schema"])
    for unsupported in ('"minimum"', '"maximum"', '"maxItems"'):
        assert unsupported not in sent  # moved into descriptions by anthropic.transform_schema
    assert "budget_tokens" not in json.dumps(captured)
    assert "tool_choice" not in captured
    assert captured["messages"][-1]["role"] == "user"  # no assistant prefill

    refusal = json.loads((FIXTURES / "anthropic_refusal.json").read_text())
    refusal.pop("_note")

    async def refuse(**kwargs: Any) -> Message:
        return Message.model_validate(refusal)

    with pytest.raises(OutputError, match="refused"):
        asyncio.run(AnthropicProvider(client=type("C", (), {"messages": _Obj(refuse)})()).complete(request()))


def test_bedrock_model_ids_prefixed() -> None:
    assert AnthropicProvider(client=object(), bedrock=True).model_id("claude-haiku-5-5") == "anthropic.claude-haiku-5-5"
    assert AnthropicProvider(client=object()).model_id("claude-haiku-5-5") == "claude-haiku-5-5"


def test_openai_adapter_against_recorded_response() -> None:
    from openai.types.chat import ChatCompletion

    payload = json.loads((FIXTURES / "openai_chat_completion.json").read_text())
    payload.pop("_note")

    async def create(**kwargs: Any) -> ChatCompletion:
        assert kwargs["response_format"]["json_schema"]["strict"] is True
        return ChatCompletion.model_validate(payload)

    client = type("C", (), {"chat": type("Chat", (), {"completions": _Obj(create)})()})()
    raw = asyncio.run(OpenAIProvider(client=client).complete(request(model="gpt-fixture")))
    assert raw.data["verdict"] == "fail"
    assert raw.input_tokens == 580


def test_only_gateway_imports_provider_sdks() -> None:
    src = Path(__file__).resolve().parents[3] / "src" / "evalgate"
    offenders = [
        p
        for p in src.rglob("*.py")
        if p.name != "gateway.py"
        and any(
            line.strip().startswith(("import anthropic", "from anthropic", "import openai", "from openai"))
            for line in p.read_text().splitlines()
        )
    ]
    assert offenders == []


def test_redaction_is_linear_on_hostile_input() -> None:
    import time

    start = time.perf_counter()
    for text in ("1" * 200_000, "a" * 200_000, ("a." * 100_000) + "@", "-1" * 100_000):
        redact(text)
    assert time.perf_counter() - start < 3.0  # quadratic patterns took minutes on these inputs
    assert redact("x" * 300_000).endswith("[TRUNCATED]")
    assert redact("call 06.12.34.56.78 on 15.03.2024") == "call [PHONE] on 15.03.2024"
