"""Judge contracts: rubric (``evalgate.rubric.v1``), label rows, verdicts and cassettes."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

RUBRIC_SCHEMA = "evalgate.rubric.v1"
VERDICT_SCHEMA_NAME = "judge_verdict.v1"


class RubricThresholds(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agreement_min: float = Field(default=0.8, ge=0, le=1)
    kappa_min: float = Field(default=0.7, ge=-1, le=1)
    position_inconsistency_max: float = Field(default=0.10, ge=0, le=1)
    verbosity_bias_max: float = Field(default=0.05, ge=0, le=1)


class Rubric(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    schema_: Literal["evalgate.rubric.v1"] = Field(alias="schema")
    name: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    version: int = Field(ge=1)
    mode: Literal["pointwise", "pairwise"]
    scale: Literal["binary", "likert5"]
    prompt: str = Field(description="Prompt file, e.g. prompts/judge_answer_correctness.v1.md")
    route: Literal["judge", "judge_hard"] = "judge"
    criteria: list[str] = Field(min_length=1)
    thresholds: RubricThresholds = Field(default_factory=RubricThresholds)
    position_swap: bool = True
    verbosity_probe: bool = True


LabelValue = Literal[0, 1, "A", "B", "tie"]


class LabelRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    rubric: str
    split: Literal["dev", "test"]
    input: str
    reference: str
    candidate: str
    candidate_b: str | None = None
    label: LabelValue
    source: Literal["construction", "maintainer"] = "construction"
    meta: dict[str, Any] = Field(default_factory=dict)


class JudgeVerdict(BaseModel):
    """``judge_verdict.v1``: the only shape a judge response may take."""

    model_config = ConfigDict(extra="forbid")

    verdict: Literal["pass", "fail", "A", "B", "tie"]
    score: float = Field(ge=0.0, le=1.0)
    reasons: list[str] = Field(default_factory=list, max_length=3)
    criteria: dict[str, Literal["met", "unmet"]] = Field(default_factory=dict)


class CassetteUsage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)


class Cassette(BaseModel):
    """A recorded provider response: ``tests/fixtures/llm/<route>/<key>.json``."""

    model_config = ConfigDict(extra="forbid")

    key: str = Field(pattern=r"^[0-9a-f]{64}$")
    route: str
    model: str
    prompt_version: str
    request_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    response: dict[str, Any]
    usage: CassetteUsage
    recorded_at: str
