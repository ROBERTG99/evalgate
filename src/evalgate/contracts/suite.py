"""Suite contract (``evalgate.suite.v1``)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from evalgate.contracts.records import Split

MetricKind = Literal[
    "exact", "json_schema", "numeric_tolerance", "tool_calls", "contains_all", "regex", "judge", "custom"
]
Direction = Literal["higher", "lower"]
SUITE_SCHEMA = "evalgate.suite.v1"


def _default_splits() -> list[Split]:
    return ["dev", "test"]


class HttpTargetSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str = Field(min_length=1)
    method: Literal["GET", "POST", "PUT"] = "POST"
    headers: dict[str, str] = Field(default_factory=dict)
    timeout_s: float = Field(default=30.0, gt=0, le=600)


class TargetSpec(BaseModel):
    """Exactly one of ``python``, ``http`` or ``langgraph``."""

    model_config = ConfigDict(extra="forbid")

    python: str | None = Field(default=None, pattern=r"^[A-Za-z_][\w.]*:[A-Za-z_]\w*$")
    http: HttpTargetSpec | None = None
    langgraph: str | None = Field(default=None, pattern=r"^[A-Za-z_][\w.]*:[A-Za-z_]\w*$")

    @model_validator(mode="after")
    def _exactly_one(self) -> TargetSpec:
        chosen = [k for k in ("python", "http", "langgraph") if getattr(self, k) is not None]
        if len(chosen) != 1:
            raise ValueError("target takes exactly one of python, http or langgraph")
        return self

    @property
    def kind(self) -> str:
        return "python" if self.python else "http" if self.http else "langgraph"


class MetricSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(pattern=r"^[a-z][a-z0-9_]*$", max_length=64)
    kind: MetricKind
    params: dict[str, Any] = Field(default_factory=dict)
    threshold: float | None = None
    direction: Direction = "higher"
    gate: bool = True


class BudgetSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_cost_usd: float | None = Field(default=None, ge=0)
    max_p95_ms: float | None = Field(default=None, gt=0)


class Suite(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    schema_: Literal["evalgate.suite.v1"] = Field(alias="schema")
    name: str = Field(pattern=r"^[a-z0-9][a-z0-9_.-]*$", max_length=64)
    description: str | None = None
    dataset: str = Field(min_length=1)
    target: TargetSpec
    concurrency: int = Field(default=8, ge=1, le=256)
    metrics: list[MetricSpec] = Field(min_length=1)
    budget: BudgetSpec | None = None
    splits: list[Split] = Field(default_factory=_default_splits)
    plugins: list[str] = Field(
        default_factory=list, description="Modules imported before the run to register custom metrics."
    )

    @model_validator(mode="after")
    def _unique_metric_names(self) -> Suite:
        names = [m.name for m in self.metrics]
        dupes = sorted({n for n in names if names.count(n) > 1})
        if dupes:
            raise ValueError(f"duplicate metric names: {', '.join(dupes)}")
        return self
