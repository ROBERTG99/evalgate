"""Offline evals for ``make eval``: run the three v1 suites on the test split, check them against the
baselines, and run the bootstrap coverage simulation. Writes evals/reports/{suite}.json,
check-{suite}.json, {suite}.md and bootstrap-coverage.json. Exits 1 when a gate fails."""

from __future__ import annotations

import json
import os
import sys
from contextlib import ExitStack
from pathlib import Path

from evalgate import config
from evalgate.report.build import load_report, write_report
from evalgate.report.markdown import render_markdown
from evalgate.runner import RunOptions, run_suite
from evalgate.stats.gate import check, sha256_file
from evalgate.stats.simulation import coverage
from evalgate.suite import load_suite

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "evals" / "reports"
SUITES = ("classify", "extract", "answer")


def main() -> int:
    sys.path.insert(0, str(ROOT / "scripts"))
    from meta_eval import toys_url

    REPORTS.mkdir(parents=True, exist_ok=True)
    ok = True
    with ExitStack() as stack:
        os.environ["EVALGATE_TOYS_URL"] = toys_url(stack)
        os.environ.pop("EVALGATE_TOY_VERSION", None)
        for suite in SUITES:
            loaded = load_suite(ROOT / f"evals/suites/{suite}.yaml", split="test")
            report = run_suite(loaded, RunOptions(split="test")).report
            path = write_report(report, REPORTS / f"{suite}.json")
            baseline_path = ROOT / f"evals/baselines/{suite}.json"
            result = check(
                report,
                report_sha256=sha256_file(path),
                baseline=load_report(baseline_path),
                baseline_sha256=sha256_file(baseline_path),
                seed=config.bootstrap_seed(),
            )
            (REPORTS / f"check-{suite}.json").write_text(
                json.dumps(result.model_dump(mode="json", by_alias=True), indent=2) + "\n", encoding="utf-8"
            )
            (REPORTS / f"{suite}.md").write_text(
                render_markdown(report, result, baseline=load_report(baseline_path)), encoding="utf-8"
            )
            print(
                f"eval: {suite} {'PASS' if result.passed else 'FAIL'} "
                + ", ".join(f"{k}={m.value:.4f}" for k, m in report.metrics.items())
            )
            ok = ok and result.passed
    sim = coverage(n_datasets=400)
    sim["command"] = "make eval (scripts/run_evals.py)"
    (REPORTS / "bootstrap-coverage.json").write_text(json.dumps(sim, indent=2) + "\n", encoding="utf-8")
    print(f"eval: bootstrap 95% CI coverage {sim['coverage']:.4f} over {sim['n_datasets']} simulated datasets")
    ok = ok and 0.92 <= sim["coverage"] <= 0.98
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
