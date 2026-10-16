"""Report contract (``evalgate.report.v1``) and check result (``evalgate.check.v1``)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from evalgate.contracts.suite import Direction

REPORT_SCHEMA = "evalgate.report.v1"
CHECK_SCHEMA = "evalgate.check.v1"


class MetricSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: float
    threshold: float | None = None
    direction: Direction = "higher"
    passed: bool
    ci_low: float | None = None
    ci_high: float | None = None


class CaseReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    split: Literal["dev", "test"]
    scores: dict[str, float]
    passed: bool
    cost_usd: float = Field(ge=0)
    latency_ms: float = Field(ge=0)
    error: str | None = None


class Report(BaseModel):
    """The stable run report. ``extensions`` is free-form and may be ignored by consumers."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    schema_: Literal["evalgate.report.v1"] = Field(alias="schema")
    suite: str
    run_id: str
    created_at: str
    git_sha: str | None = None
    mode: Literal["offline", "live"]
    models: list[str] = Field(default_factory=list)
    prompt_hashes: dict[str, str] = Field(default_factory=dict)
    n_cases: int = Field(ge=0)
    metrics: dict[str, MetricSummary]
    cost_usd_total: float = Field(ge=0)
    cost_usd_per_case: float = Field(ge=0)
    latency_p50_ms: float = Field(ge=0)
    latency_p95_ms: float = Field(ge=0)
    cases: list[CaseReport]
    extensions: dict[str, Any] | None = None


FailureReason = Literal["threshold", "regression", "budget_cost", "budget_p95", "error"]


class CheckFailure(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metric: str
    reason: FailureReason
    value: float | None = None
    threshold: float | None = None
    delta_pp: float | None = None
    ci_low_pp: float | None = None
    ci_high_pp: float | None = None


class Comparison(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metric: str
    baseline: float
    candidate: float
    delta_pp: float
    ci_low_pp: float
    ci_high_pp: float
    n_paired: int = Field(ge=0)


class CheckResult(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    schema_: Literal["evalgate.check.v1"] = Field(default="evalgate.check.v1", alias="schema")
    report_sha256: str
    baseline_sha256: str | None = None
    max_regression_pp: float
    seed: int
    resamples: int
    passed: bool
    failures: list[CheckFailure] = Field(default_factory=list)
    comparisons: list[Comparison] = Field(default_factory=list)
