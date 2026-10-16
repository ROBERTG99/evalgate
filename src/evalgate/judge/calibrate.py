"""``evalgate calibrate``: measure a judge against labelled items before adopting it (FR-5).

Reports agreement, Cohen's kappa, the confusion matrix, position inconsistency, verbosity bias and
injection pass-through, and passes only when every rubric threshold holds.
"""

from __future__ import annotations

import asyncio
import json
from collections import Counter
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from evalgate.contracts import LabelRow, MetricSpec
from evalgate.errors import InvalidInputError
from evalgate.judge.context import JudgeContext
from evalgate.judge.metric import JudgeMetric

# Neutral padding (no facts, no numbers) for the verbosity probe: ~20 words.
VERBOSE_PREFIX = (
    "To give you the complete picture, here is a careful and thorough explanation of how this works for you. "
)


def cohen_kappa(labels: list[str], preds: list[str]) -> float:
    """Cohen's kappa for two raters over the categories that appear in either list."""
    n = len(labels)
    if n == 0:
        return 0.0
    po = sum(a == b for a, b in zip(labels, preds, strict=True)) / n
    cl, cp = Counter(labels), Counter(preds)
    pe = sum((cl[k] / n) * (cp[k] / n) for k in set(cl) | set(cp))
    if pe >= 1.0:
        return 1.0 if po == 1.0 else 0.0
    return (po - pe) / (1 - pe)


def confusion(labels: list[str], preds: list[str]) -> dict[str, dict[str, int]]:
    cats = sorted(set(labels) | set(preds))
    matrix = {a: dict.fromkeys(cats, 0) for a in cats}
    for a, b in zip(labels, preds, strict=True):
        matrix[a][b] += 1
    return matrix


def load_labels(path: Path) -> list[LabelRow]:
    if not path.is_file():
        raise InvalidInputError(str(path), "", "labels file not found")
    rows = []
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            rows.append(LabelRow.model_validate(json.loads(line)))
        except (json.JSONDecodeError, ValidationError) as exc:
            raise InvalidInputError(str(path), f"line {i}", str(exc).splitlines()[0]) from exc
    return rows


def _label(value: object) -> str:
    return "1" if value == 1 else "0" if value == 0 else str(value)


async def _run(metric: JudgeMetric, rows: list[LabelRow]) -> dict[str, Any]:
    rubric = metric.rubric
    labels: list[str] = []
    preds: list[str] = []
    inconsistent = 0
    injections = 0
    injection_passes = 0
    padded_shift: list[float] = []
    disagreements = []
    for row in rows:
        score = await metric.judge(row.input, row.reference, row.candidate, row.candidate_b or "")
        if rubric.mode == "pairwise":
            pred = {1.0: "A", 0.0: "B"}.get(score.value, "tie")
        else:
            pred = "1" if score.passed else "0"
        if score.details.get("position_inconsistent"):
            inconsistent += 1
        if row.meta.get("construction") == "injection":
            injections += 1
            injection_passes += int(pred == "1")
        labels.append(_label(row.label))
        preds.append(pred)
        if labels[-1] != pred:
            disagreements.append(
                {"id": row.id, "label": labels[-1], "pred": pred, "construction": row.meta.get("construction")}
            )
        if rubric.verbosity_probe:
            padded = await metric.judge(row.input, row.reference, VERBOSE_PREFIX + row.candidate, row.candidate_b or "")
            padded_shift.append(padded.value - score.value)
    n = len(rows)
    agreement = sum(a == b for a, b in zip(labels, preds, strict=True)) / n if n else 0.0
    return {
        "n": n,
        "agreement": round(agreement, 6),
        "kappa": round(cohen_kappa(labels, preds), 6),
        "confusion": confusion(labels, preds),
        "position_inconsistency": round(inconsistent / n, 6) if n else 0.0,
        "verbosity_bias": round(sum(padded_shift) / len(padded_shift), 6) if padded_shift else 0.0,
        "injection_items": injections,
        "injection_pass_through": round(injection_passes / injections, 6) if injections else 0.0,
        "disagreements": disagreements[:50],
    }


def calibrate(
    rubric_path: Path, labels_path: Path, split: str = "test", ctx: JudgeContext | None = None
) -> dict[str, Any]:
    if split not in ("dev", "test"):
        raise InvalidInputError("--split", "", "split must be dev or test")
    ctx = ctx or JudgeContext.create()
    spec = MetricSpec(name="calibration", kind="judge", params={"rubric": str(rubric_path)})
    metric = JudgeMetric(spec, ctx)
    rubric = metric.rubric
    rows = [r for r in load_labels(labels_path) if r.rubric == rubric.name and r.split == split]
    if not rows:
        raise InvalidInputError(str(labels_path), "", f"no {split} labels for rubric {rubric.name!r}")
    stats = asyncio.run(_run(metric, rows))
    t = rubric.thresholds
    checks = {
        "agreement": stats["agreement"] >= t.agreement_min,
        "kappa": stats["kappa"] >= t.kappa_min,
        "position_inconsistency": stats["position_inconsistency"] <= t.position_inconsistency_max,
        "verbosity_bias": abs(stats["verbosity_bias"]) <= t.verbosity_bias_max,
        "injection_pass_through": stats["injection_pass_through"] == 0.0,
    }
    return {
        "schema": "evalgate.calibration.v1",
        "rubric": f"{rubric.name}.v{rubric.version}",
        "prompt_version": metric.loaded.prompt_version,
        "prompt_sha256": metric.loaded.prompt_sha256,
        "labels": str(labels_path),
        "split": split,
        "mode": ctx.mode,
        "models": sorted(ctx.models_used()),
        "thresholds": t.model_dump(),
        **stats,
        "checks": checks,
        "passed": all(checks.values()),
        "judge_calls": ctx.judge_calls,
    }


def render_calibration(result: dict[str, Any]) -> str:
    t = result["thresholds"]
    lines = [
        f"calibration {result['rubric']} on {result['n']} {result['split']} labels "
        f"({result['mode']}, models {', '.join(result['models']) or 'none'}): {'PASS' if result['passed'] else 'FAIL'}",
        f"  agreement {result['agreement']:.3f} (min {t['agreement_min']}), kappa {result['kappa']:.3f} "
        f"(min {t['kappa_min']})",
        f"  position inconsistency {result['position_inconsistency']:.3f} (max {t['position_inconsistency_max']}), "
        f"verbosity bias {result['verbosity_bias']:+.3f} (max |{t['verbosity_bias_max']}|), "
        f"injection pass-through {result['injection_pass_through']:.3f} over {result['injection_items']} items",
        "  confusion (rows = label, columns = judge):",
    ]
    cats = list(result["confusion"])
    lines.append("    " + "".join(f"{c:>6}" for c in ["", *cats]))
    for label in cats:
        lines.append("    " + f"{label:>6}" + "".join(f"{result['confusion'][label][p]:>6}" for p in cats))
    return "\n".join(lines)
