"""Provider-neutral request and response records."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class LLMRequest:
    route: str
    model: str
    prompt_version: str
    system: str
    messages: list[dict[str, str]]
    schema_name: str
    schema: dict[str, Any]
    effort: str = "low"
    max_tokens: int = 2048


@dataclass
class RawResponse:
    data: dict[str, Any]
    input_tokens: int
    output_tokens: int
    stop_reason: str = "end_turn"
    model: str = ""
    source: str = "provider"  # provider | cassette | rules


@dataclass
class LLMResponse:
    data: dict[str, Any]
    input_tokens: int
    output_tokens: int
    cost_usd: float
    latency_ms: float
    model: str
    provider: str
    source: str
    attempts: int = 1
    extra: dict[str, Any] = field(default_factory=dict)


class ProviderError(Exception):
    """A provider failure. ``retriable`` covers 408, 409, 429, 5xx and connection errors."""

    def __init__(self, message: str, retriable: bool, status: int | None = None) -> None:
        super().__init__(message)
        self.retriable = retriable
        self.status = status


class OutputError(Exception):
    """The model answered but the output is unusable (refusal, max_tokens, invalid JSON or schema)."""

    cost_usd: float = 0.0  # what the unusable answer still cost (set by the gateway)
