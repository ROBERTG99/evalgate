"""Pydantic v2 contracts; the source of truth for ``schemas/*.json`` (``make schemas``)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from evalgate.contracts.judge import (
    Cassette,
    CassetteUsage,
    JudgeVerdict,
    LabelRow,
    Rubric,
    RubricThresholds,
)
from evalgate.contracts.records import Case, MetricScore, StepRecord, TargetResult
from evalgate.contracts.report import (
    CaseReport,
    CheckFailure,
    CheckResult,
    Comparison,
    MetricSummary,
    Report,
)
from evalgate.contracts.suite import BudgetSpec, HttpTargetSpec, MetricSpec, Suite, TargetSpec

#: Schema file name (without ``.json``) to model. ``evalgate schema <short>`` uses ``SHORT_NAMES``.
SCHEMA_MODELS: dict[str, type[BaseModel]] = {
    "evalgate.suite.v1": Suite,
    "evalgate.report.v1": Report,
    "evalgate.check.v1": CheckResult,
    "evalgate.rubric.v1": Rubric,
    "cassette.v1": Cassette,
    "evalgate.dataset_row.v1": Case,
    "evalgate.label_row.v1": LabelRow,
    "judge_verdict.v1": JudgeVerdict,
    "evalgate.step_record.v1": StepRecord,
}
SHORT_NAMES: dict[str, str] = {
    "suite": "evalgate.suite.v1",
    "report": "evalgate.report.v1",
    "check": "evalgate.check.v1",
    "rubric": "evalgate.rubric.v1",
    "cassette": "cassette.v1",
    "dataset": "evalgate.dataset_row.v1",
    "label": "evalgate.label_row.v1",
    "verdict": "judge_verdict.v1",
    "step": "evalgate.step_record.v1",
}


def json_schema(name: str) -> dict[str, Any]:
    """Return the JSON Schema for a schema name such as ``evalgate.report.v1``."""
    model = SCHEMA_MODELS[name]
    schema = model.model_json_schema(by_alias=True, mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"https://github.com/ROBERTG99/evalgate/schemas/{name}.json"
    schema["title"] = name
    return schema


__all__ = [
    "SCHEMA_MODELS",
    "SHORT_NAMES",
    "BudgetSpec",
    "Case",
    "CaseReport",
    "Cassette",
    "CassetteUsage",
    "CheckFailure",
    "CheckResult",
    "Comparison",
    "HttpTargetSpec",
    "JudgeVerdict",
    "LabelRow",
    "MetricScore",
    "MetricSpec",
    "MetricSummary",
    "Report",
    "Rubric",
    "RubricThresholds",
    "StepRecord",
    "Suite",
    "TargetResult",
    "TargetSpec",
    "json_schema",
]
