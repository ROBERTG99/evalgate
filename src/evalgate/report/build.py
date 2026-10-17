"""Build, write and read ``evalgate.report.v1`` documents."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from evalgate.accounting import percentile
from evalgate.contracts import CaseReport, MetricScore, MetricSummary, Report, Suite
from evalgate.errors import InvalidInputError
from evalgate.metrics.base import worst_score
from evalgate.suite.limits import MAX_REPORT_BYTES, check_file_size


@dataclass
class CaseOutcome:
    case_id: str
    split: str
    scores: list[MetricScore]
    passed: bool
    cost_usd: float
    latency_ms: float
    attempts: int = 1
    error: str | None = None
    steps: list[Any] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)


def git_sha() -> str | None:
    env = os.environ.get("GITHUB_SHA")
    if env:
        return env
    git = shutil.which("git")
    if git is None:
        return None
    try:
        out = subprocess.run(  # noqa: S603 - fixed argv
            [git, "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() or None if out.returncode == 0 else None


def build_report(
    suite: Suite,
    outcomes: list[CaseOutcome],
    *,
    run_id: str,
    mode: str,
    models: list[str],
    prompt_hashes: dict[str, str],
    seed: int,
    resamples: int = 10_000,
    extensions: dict[str, Any] | None = None,
    created_at: str | None = None,
    sha: str | None = None,
) -> Report:
    from evalgate.stats.bootstrap import mean_ci

    outcomes = sorted(outcomes, key=lambda o: o.case_id)
    metrics: dict[str, MetricSummary] = {}
    for spec in suite.metrics:
        missing = worst_score(spec.direction)
        values = [next((s.value for s in o.scores if s.name == spec.name), missing) for o in outcomes]
        ci = mean_ci(values, seed=seed, resamples=resamples)
        value = ci.estimate
        if spec.threshold is None:
            passed = True
        elif spec.direction == "higher":
            passed = value >= spec.threshold
        else:
            passed = value <= spec.threshold
        metrics[spec.name] = MetricSummary(
            value=round(value, 10),
            threshold=spec.threshold,
            direction=spec.direction,
            passed=passed,
            ci_low=round(ci.low, 10),
            ci_high=round(ci.high, 10),
        )
    latencies = [o.latency_ms for o in outcomes]
    cost_total = sum(o.cost_usd for o in outcomes)
    cases = [
        CaseReport(
            id=o.case_id,
            split=o.split,
            scores={s.name: s.value for s in o.scores},
            passed=o.passed,
            cost_usd=round(o.cost_usd, 10),
            latency_ms=round(o.latency_ms, 3),
            error=o.error,
        )
        for o in outcomes
    ]
    return Report.model_validate(
        {
            "schema": "evalgate.report.v1",
            "suite": suite.name,
            "run_id": run_id,
            "created_at": created_at or datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
            "git_sha": sha if sha is not None else git_sha(),
            "mode": mode,
            "models": sorted(set(models)),
            "prompt_hashes": dict(sorted(prompt_hashes.items())),
            "n_cases": len(cases),
            "metrics": metrics,
            "cost_usd_total": round(cost_total, 10),
            "cost_usd_per_case": round(cost_total / len(cases), 10) if cases else 0.0,
            "latency_p50_ms": round(percentile(latencies, 50), 3),
            "latency_p95_ms": round(percentile(latencies, 95), 3),
            "cases": [c.model_dump() for c in cases],
            "extensions": extensions,
        }
    )


def report_json(report: Report) -> str:
    return json.dumps(report.model_dump(mode="json", by_alias=True), indent=2, ensure_ascii=False) + "\n"


def write_report(report: Report, path: str | Path) -> Path:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(out.suffix + ".tmp")
    tmp.write_text(report_json(report), encoding="utf-8")
    tmp.replace(out)
    return out


def load_report(path: str | Path) -> Report:
    p = Path(path)
    if not p.is_file():
        raise InvalidInputError(str(p), "", "report not found")
    check_file_size(p, MAX_REPORT_BYTES, "report")
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise InvalidInputError(str(p), "", f"invalid JSON: {exc}") from exc
    try:
        return Report.model_validate(data)
    except ValidationError as exc:
        from evalgate.suite.loader import validation_error

        raise validation_error(p, exc) from exc
