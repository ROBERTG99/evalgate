"""Shared runtime records: dataset cases, steps, target results and metric scores."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

StepKind = Literal["llm", "tool", "retrieval", "judge", "target", "other"]
StepStatus = Literal["ok", "error", "timeout", "skipped"]
Split = Literal["dev", "test"]


class StepRecord(BaseModel):
    """One step of a target or judge call; the record shared across tools."""

    model_config = ConfigDict(extra="forbid")

    run_id: str = ""
    task_id: str = ""
    step: int = Field(default=0, ge=0)
    node: str = "target"
    kind: StepKind = "other"
    model: str | None = None
    prompt_version: str | None = None
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    cost_usd: float = Field(default=0.0, ge=0)
    latency_ms: float = Field(default=0.0, ge=0)
    status: StepStatus = "ok"
    error: str | None = None
    started_at: datetime | None = None


class TargetResult(BaseModel):
    """What a target returns for one case."""

    model_config = ConfigDict(extra="forbid")

    output: dict[str, Any] | str
    steps: list[StepRecord] = Field(default_factory=list)
    cost_usd: float = Field(default=0.0, ge=0)
    latency_ms: float = Field(default=0.0, ge=0)
    trace_id: str | None = None


class MetricScore(BaseModel):
    """The score of one metric on one case. ``value`` is in [0, 1]."""

    model_config = ConfigDict(extra="forbid")

    name: str
    value: float = Field(ge=0.0, le=1.0)
    passed: bool
    details: dict[str, Any] = Field(default_factory=dict)


class Case(BaseModel):
    """A dataset row (one JSONL line)."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=200)
    split: Split
    input: dict[str, Any]
    expected: dict[str, Any] | None = None
    tags: list[str] = Field(default_factory=list)
    meta: dict[str, Any] = Field(default_factory=dict)
