"""Meta-evaluation (FR-14): does the gate catch the 30 injected regressions and pass the 20 neutral changes?

Each catalogued variant of the toy targets is run on its suite's test split (selected with the
``X-Toy-Variant`` header) and checked against the v1 baseline with the production gate rule.
Writes ``evals/reports/meta-eval.json``; exits 1 when detection < 0.90 or false positives > 0.10.
Uses ``EVALGATE_TOYS_URL`` when it answers, otherwise starts the toy targets in-process.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import defaultdict
from contextlib import ExitStack
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from evalgate import config
from evalgate.report.build import git_sha, load_report
from evalgate.runner import RunOptions, run_suite
from evalgate.stats.gate import MIN_PAIRED, check
from evalgate.suite import load_suite

ROOT = Path(__file__).resolve().parents[1]
MAX_REGRESSION_PP = 1.0
DETECTION_MIN = 0.90
FALSE_POSITIVE_MAX = 0.10


def toys_url(stack: ExitStack) -> str:
    url = os.environ.get("EVALGATE_TOYS_URL", "").rstrip("/")
    if url:
        try:
            if httpx.get(f"{url}/healthz", timeout=2).status_code == 200:
                return url
        except httpx.HTTPError:
            pass
    from toy_targets.server import running

    return stack.enter_context(running())


def binom_cdf(k: int, n: int, p: float) -> float:
    total, term = 0.0, (1 - p) ** n
    for i in range(k + 1):
        total += term
        term = term * (n - i) / (i + 1) * p / (1 - p) if p < 1 else 0.0
    return min(1.0, total)


def clopper_pearson(k: int, n: int, level: float = 0.95) -> tuple[float, float]:
    """Exact two-sided binomial interval by bisection on the binomial CDF (no SciPy needed)."""
    if n == 0:
        return 0.0, 1.0
    alpha = 1 - level

    def solve(target: float, kk: int) -> float:
        lo, hi = 0.0, 1.0
        for _ in range(100):
            mid = (lo + hi) / 2
            if binom_cdf(kk, n, mid) > target:
                lo = mid
            else:
                hi = mid
        return (lo + hi) / 2

    lower = 0.0 if k == 0 else solve(1 - alpha / 2, k - 1)
    upper = 1.0 if k == n else solve(alpha / 2, k)
    return round(lower, 4), round(upper, 4)


def rate(hits: int, n: int) -> float:
    return round(hits / n, 6) if n else 0.0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / "evals/reports/meta-eval.json")
    parser.add_argument("--resamples", type=int, default=10_000)
    args = parser.parse_args()
    variants = [json.loads(x) for x in (ROOT / "evals/datasets/meta/variants.v1.jsonl").read_text().splitlines()]
    baselines = {s: load_report(ROOT / f"evals/baselines/{s}.json") for s in ("classify", "extract", "answer")}
    started = time.monotonic()
    rows: list[dict[str, Any]] = []
    with ExitStack() as stack:
        url = toys_url(stack)
        os.environ["EVALGATE_TOYS_URL"] = url
        for v in variants:
            system = v["input"]["system"]
            loaded = load_suite(ROOT / f"evals/suites/{system}.yaml", split="test")
            assert loaded.suite.target.http is not None
            loaded.suite.target.http.headers = {"X-Toy-Variant": v["id"]}
            report = run_suite(
                loaded, RunOptions(split="test", cache_mode="off", use_store=False, resamples=args.resamples)
            ).report
            result = check(
                report,
                report_sha256=v["id"],
                baseline=baselines[system],
                max_regression_pp=MAX_REGRESSION_PP,
                seed=config.bootstrap_seed(),
                resamples=args.resamples,
            )
            rows.append(
                {
                    "id": v["id"],
                    "split": v["split"],
                    "system": system,
                    "mutation": v["meta"]["mutation"],
                    "params": v["meta"]["params"],
                    "regression": v["expected"]["regression"],
                    "kind": v["expected"]["kind"],
                    "detected": not result.passed,
                    "failures": [
                        {"metric": f.metric, "reason": f.reason, "delta_pp": f.delta_pp} for f in result.failures
                    ],
                    "metrics": {k: m.value for k, m in report.metrics.items()},
                    "cost_usd_total": report.cost_usd_total,
                    "latency_p95_ms": report.latency_p95_ms,
                }
            )
            mark = "DETECTED" if not result.passed else "passed"
            print(
                f"{v['id']} {system:8} {v['meta']['mutation']:20} regression={v['expected']['regression']!s:5} {mark}"
            )

    def summary(subset: list[dict[str, Any]]) -> dict[str, Any]:
        reg = [r for r in subset if r["regression"]]
        neu = [r for r in subset if not r["regression"]]
        det = sum(r["detected"] for r in reg)
        fp = sum(r["detected"] for r in neu)
        reasons: dict[str, int] = {}
        for r in reg:
            for reason in sorted({f["reason"] for f in r["failures"]}):
                reasons[reason] = reasons.get(reason, 0) + 1
        return {
            "regressions": len(reg),
            "detected": det,
            "detection_rate": rate(det, len(reg)),
            "detection_ci95": clopper_pearson(det, len(reg)),
            "neutral": len(neu),
            "false_positives": fp,
            "false_positive_rate": rate(fp, len(neu)),
            "false_positive_ci95": clopper_pearson(fp, len(neu)),
            "regressions_by_failure_reason": reasons,
        }

    overall = summary(rows)
    groups: dict[str, dict[str, list[dict[str, Any]]]] = {
        "split": defaultdict(list),
        "system": defaultdict(list),
        "kind": defaultdict(list),
    }
    for r in rows:
        groups["split"][r["split"]].append(r)
        groups["system"][r["system"]].append(r)
        groups["kind"][r["kind"]].append(r)
    passed = overall["detection_rate"] >= DETECTION_MIN and overall["false_positive_rate"] <= FALSE_POSITIVE_MAX
    out = {
        "schema": "evalgate.meta_eval.v1",
        "created_at": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "git_sha": git_sha(),
        "mode": "offline",
        "command": "make meta-eval",
        "seed": config.bootstrap_seed(),
        "resamples": args.resamples,
        "max_regression_pp": MAX_REGRESSION_PP,
        "min_paired": MIN_PAIRED,
        "baselines": {s: f"evals/baselines/{s}.json" for s in baselines},
        "thresholds": {"detection_min": DETECTION_MIN, "false_positive_max": FALSE_POSITIVE_MAX},
        **overall,
        "by": {name: {k: summary(v) for k, v in sorted(g.items())} for name, g in groups.items()},
        "passed": passed,
        "seconds": round(time.monotonic() - started, 1),
        "variants": rows,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(
        f"meta-eval: detected {overall['detected']}/{overall['regressions']} regressions "
        f"({overall['detection_rate']:.2%}), {overall['false_positives']}/{overall['neutral']} neutral changes failed "
        f"({overall['false_positive_rate']:.2%}) -> {'PASS' if passed else 'FAIL'}; wrote {args.out}"
    )
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
