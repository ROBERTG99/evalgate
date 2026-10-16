"""Test factories: suites, datasets, reports and cases with fixed seeds."""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any

import yaml

from evalgate.contracts import Case, Report, TargetResult


def case(i: int = 1, split: str = "test", **kw: Any) -> Case:
    data: dict[str, Any] = {"id": f"c-{i:04d}", "split": split, "input": {"text": f"t{i}"}, "expected": {}}
    data.update(kw)
    return Case.model_validate(data)


def result(output: Any = None, **kw: Any) -> TargetResult:
    return TargetResult(output=output if output is not None else {}, **kw)


def write_dataset(path: Path, rows: list[dict[str, Any]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))
    return path


def rows(n: int, split: str = "test", **extra: Any) -> list[dict[str, Any]]:
    return [
        {
            "id": f"r-{i:04d}",
            "split": split,
            "input": {"text": f"t{i}", "i": i},
            "expected": {"label": "a"},
            "tags": [],
            "meta": {},
            **extra,
        }
        for i in range(n)
    ]


def write_suite(path: Path, dataset: Path, **overrides: Any) -> Path:
    suite: dict[str, Any] = {
        "schema": "evalgate.suite.v1",
        "name": "t",
        "dataset": str(dataset),
        "target": {"python": "tests.fixtures.targets:echo"},
        "concurrency": 4,
        "metrics": [
            {
                "name": "acc",
                "kind": "exact",
                "params": {"actual": "output.label", "expected": "expected.label"},
                "threshold": 0.5,
                "direction": "higher",
                "gate": True,
            }
        ],
        "splits": ["dev", "test"],
    }
    suite.update(overrides)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(suite, sort_keys=False))
    return path


def make_report(
    scores: dict[str, list[float]],
    suite: str = "s",
    seed: int = 0,
    threshold: float | None = None,
    direction: str = "higher",
    extensions: dict[str, Any] | None = None,
    p95: float = 100.0,
    cost: float = 0.0,
    ids: list[str] | None = None,
) -> Report:
    """A report whose cases carry the given per-metric scores (same length lists)."""
    n = len(next(iter(scores.values())))
    ids = ids or [f"c-{i:04d}" for i in range(n)]
    rng = random.Random(seed)
    cases = [
        {
            "id": ids[i],
            "split": "test",
            "scores": {m: v[i] for m, v in scores.items()},
            "passed": True,
            "cost_usd": cost / n if n else 0.0,
            "latency_ms": rng.uniform(10, 20),
            "error": None,
        }
        for i in range(n)
    ]
    metrics = {
        m: {
            "value": sum(v) / n,
            "threshold": threshold,
            "direction": direction,
            "passed": True,
            "ci_low": None,
            "ci_high": None,
        }
        for m, v in scores.items()
    }
    return Report.model_validate(
        {
            "schema": "evalgate.report.v1",
            "suite": suite,
            "run_id": "00000000-0000-7000-8000-000000000000",
            "created_at": "2026-10-16T00:00:00Z",
            "git_sha": None,
            "mode": "offline",
            "models": [],
            "prompt_hashes": {},
            "n_cases": n,
            "metrics": metrics,
            "cost_usd_total": cost,
            "cost_usd_per_case": cost / n if n else 0.0,
            "latency_p50_ms": p95 / 2,
            "latency_p95_ms": p95,
            "cases": cases,
            "extensions": extensions,
        }
    )
