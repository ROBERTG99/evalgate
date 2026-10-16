"""Live evals (``make eval-live``): calibrate the answer-correctness judge on its test labels with a real model.

- Needs a provider key (``EVALGATE_LLM_PROVIDER`` = anthropic (default here), bedrock or openai); without one
  it writes ``evals/reports/live-eval.json`` with ``ran: false`` and exits 2.
- Prints the cost estimate first and stops before any call when it exceeds ``LIVE_EVAL_BUDGET_USD`` (default 2).
- The gateway enforces the same budget as a hard stop during the run (exit 3).
- With ``EVALGATE_RECORD_CASSETTES=1`` (``make record-fixtures``) responses are saved as cassettes.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from evalgate import config
from evalgate.budget import enforce_estimate, estimate_judge_cost
from evalgate.errors import BudgetAbortError
from evalgate.judge.calibrate import calibrate, load_labels
from evalgate.judge.context import JudgeContext, load_rubric
from evalgate.report.build import git_sha

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "evals" / "reports" / "live-eval.json"
RUBRIC = ROOT / "evals" / "rubrics" / "answer_correctness.v1.yaml"
LABELS = ROOT / "evals" / "datasets" / "judge" / "answer_correctness.labels.v1.jsonl"
KEYS = {
    "anthropic": ["ANTHROPIC_API_KEY"],
    "openai": ["OPENAI_API_KEY"],
    "bedrock": ["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"],
}


def missing_credentials(provider: str) -> list[str]:
    return [k for k in KEYS.get(provider, []) if not os.environ.get(k)]


def write(payload: dict[str, Any], out: Path = OUT) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def plan(n_items: int, model: str) -> Any:
    # position swap (2 calls) + verbosity probe (2 more calls) per labelled item
    return estimate_judge_cost(n_items, [(model, 4)])


def run(
    provider_name: str | None = None, provider: Any = None, out: Path = OUT, budget_usd: float | None = None
) -> int:
    from evalgate.llm.gateway import Gateway

    name = provider_name or os.environ.get("EVALGATE_LLM_PROVIDER", "anthropic")
    if name == "fake":
        name = "anthropic"
    stamp = datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
    missing = [] if provider is not None else missing_credentials(name)
    if missing:
        reason = f"{', '.join(missing)} not set"
        write(
            {"schema": "evalgate.live_eval.v1", "ran": False, "reason": reason, "provider": name, "created_at": stamp},
            out,
        )
        print(f"eval-live: live evals were not run: {reason}", file=sys.stderr)
        return 2
    budget = config.live_budget_usd() if budget_usd is None else budget_usd
    route = load_rubric(RUBRIC).rubric.route
    model = config.judge_hard_model() if route == "judge_hard" else config.judge_model()
    items = [r for r in load_labels(LABELS) if r.rubric == "answer_correctness" and r.split == "test"]
    estimate = plan(len(items), model)
    estimate = estimate.__class__(estimate.calls, estimate.cost_usd, budget)
    print(f"eval-live: {estimate.describe()}", file=sys.stderr)
    base = {
        "schema": "evalgate.live_eval.v1",
        "provider": name,
        "model": model,
        "created_at": stamp,
        "git_sha": git_sha(),
        "estimate_usd": round(estimate.cost_usd, 6),
        "budget_usd": budget,
    }
    try:
        enforce_estimate(estimate)
        gateway = Gateway(provider, provider_name=name, budget_usd=budget)
        ctx = JudgeContext(gateway, cache=None, base_dir=ROOT)
        result = calibrate(RUBRIC, LABELS, split="test", ctx=ctx)
    except BudgetAbortError as exc:
        write({**base, "ran": False, "stopped_at_budget": True, "reason": str(exc)}, out)
        print(f"eval-live: stopped: {exc}", file=sys.stderr)
        return 3
    write(
        {**base, "ran": True, "mode": "live", "cost_usd": round(gateway.guard.spent_usd, 6), "calibration": result}, out
    )
    print(
        f"eval-live: {result['rubric']} live agreement {result['agreement']:.3f}, kappa {result['kappa']:.3f}, "
        f"cost USD {gateway.guard.spent_usd:.4f}",
        file=sys.stderr,
    )
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(run())
