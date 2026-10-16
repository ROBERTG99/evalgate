"""FakeLLM: the offline provider. Replays cassettes when present, else answers with rules (FakeJudge)."""

from __future__ import annotations

from pathlib import Path

from evalgate.judge.fake import FakeJudge
from evalgate.llm import cassette as cassettes
from evalgate.llm.types import LLMRequest, RawResponse

FAKE_MODEL = "fake-judge"


class FakeLLM:
    name = "fake"

    def __init__(self, cassette_dir: Path | None = None, use_cassettes: bool = True) -> None:
        self.cassette_dir = cassette_dir if cassette_dir is not None else cassettes.default_dir()
        self.use_cassettes = use_cassettes
        self.judge = FakeJudge()
        self.calls = 0

    async def complete(self, req: LLMRequest) -> RawResponse:
        self.calls += 1
        if self.use_cassettes:
            recorded = cassettes.load(self.cassette_dir, req)  # raises CassetteMismatch on a stale cassette
            if recorded is not None:
                return RawResponse(
                    data=recorded.response,
                    input_tokens=recorded.usage.input_tokens,
                    output_tokens=recorded.usage.output_tokens,
                    model=recorded.model,
                    source="cassette",
                )
        user = "\n".join(m["content"] for m in req.messages if m["role"] == "user")
        data = self.judge.verdict(user)
        tin, tout = self.judge.usage(user, data)
        return RawResponse(data=data, input_tokens=tin, output_tokens=tout, model=FAKE_MODEL, source="rules")
