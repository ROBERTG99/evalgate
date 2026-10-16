from pathlib import Path

from evalgate.adapters.promptfoo import import_promptfoo
from evalgate.runner import RunOptions, run_suite
from evalgate.suite import load_suite

ROOT = Path(__file__).resolve().parents[2]


def test_imported_sample_suite_runs(tmp_path: Path, toys_url: str) -> None:
    suite_path, _, _ = import_promptfoo(
        ROOT / "evals/datasets/promptfoo/promptfooconfig.yaml", tmp_path, name="pf", base_url=toys_url
    )
    result = run_suite(load_suite(suite_path), RunOptions(home=tmp_path / "home", resamples=200))
    report = result.report
    assert report.n_cases == 12
    assert all(c.error is None for c in report.cases)
    assert report.metrics["equals"].value >= 0.8
    assert report.metrics["regex"].value == 1.0
    # rows without a contains assert are skipped, not scored as problems (T-45 review)
    assert report.metrics["contains"].value == 1.0
    assert not any("problem" in s.details for o in result.outcomes for s in o.scores)
