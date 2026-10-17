"""Calibrate every rubric in evals/rubrics/ on its test labels; write evals/reports/calibration-*.json."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from evalgate.judge.calibrate import calibrate, render_calibration

ROOT = Path(__file__).resolve().parents[1]
LABELS = {
    "answer_correctness": "evals/datasets/judge/answer_correctness.labels.v1.jsonl",
    "pairwise_preference": "evals/datasets/judge/answer_correctness.labels.v1.jsonl",
    "rubric_adherence": "evals/datasets/judge/rubric_adherence.labels.v1.jsonl",
}


def main() -> int:
    out_dir = ROOT / "evals" / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    ok = True
    for rubric_path in sorted((ROOT / "evals" / "rubrics").glob("*.yaml")):
        name = rubric_path.name.split(".")[0]
        if name not in LABELS:
            print(f"calibration: no labels for {rubric_path.name}; not adoptable", file=sys.stderr)
            ok = False
            continue
        result = calibrate(rubric_path, ROOT / LABELS[name], split="test")
        (out_dir / f"calibration-{name}.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(render_calibration(result))
        ok = ok and result["passed"]
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
