"""Seed the viewer: run the v1 and v2 toy suites (test split, offline) and write their reports.

Used by the compose `seed` service (``make seed``). Synthetic data, seed 1337, FakeJudge.
Usage: ``python scripts/seed_reports.py --out /reports``
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from evalgate.report.build import write_report
from evalgate.runner import RunOptions, run_suite
from evalgate.suite import load_suite

RUNS = [
    ("classify", "v1"),
    ("extract", "v1"),
    ("answer", "v1"),
    ("classify", "v2"),
    ("extract", "v2"),
    ("answer", "v2"),
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("reports"))
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    os.chdir(args.root)
    for suite, version in RUNS:
        os.environ["EVALGATE_TOY_VERSION"] = version
        loaded = load_suite(Path(f"evals/suites/{suite}.yaml"), split="test")
        report = run_suite(loaded, RunOptions(split="test")).report
        path = write_report(report, args.out / f"{suite}-{version}.json")
        ok = all(m.passed for m in report.metrics.values())
        print(f"seed: {suite} {version} -> {path} ({report.n_cases} cases, thresholds {'met' if ok else 'missed'})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
