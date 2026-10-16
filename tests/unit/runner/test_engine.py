import asyncio
import random
from pathlib import Path
from typing import Any

import pytest

from evalgate.contracts import TargetResult
from evalgate.runner import RunOptions, run_suite
from evalgate.runner.retry import CaseFailure, backoff_delay, call_with_retries
from evalgate.suite import load_suite
from evalgate.targets.base import RetriableTargetError, TargetError
from tests.factories import rows, write_dataset, write_suite


def suite_for(tmp_path: Path, n: int, **overrides: Any):
    data = write_dataset(tmp_path / "d.jsonl", rows(n))
    return load_suite(write_suite(tmp_path / "s.yaml", data, **overrides), split="test")


def opts(tmp_path: Path, **kw: Any) -> RunOptions:
    return RunOptions(split="test", home=tmp_path / "home", use_store=False, resamples=200, **kw)


def test_semaphore_bound(tmp_path: Path) -> None:
    in_flight = 0
    peak = 0

    async def target(case_input: dict[str, Any]) -> TargetResult:
        nonlocal in_flight, peak
        in_flight += 1
        peak = max(peak, in_flight)
        await asyncio.sleep(0.01)
        in_flight -= 1
        return TargetResult(output={"label": "a"})

    loaded = suite_for(tmp_path, 40, concurrency=4)
    result = run_suite(loaded, opts(tmp_path, target=target))
    assert peak == 4
    assert result.report.n_cases == 40
    assert result.report.metrics["acc"].value == 1.0


def test_timeout_scores_zero(tmp_path: Path) -> None:
    async def target(case_input: dict[str, Any]) -> TargetResult:
        if case_input["i"] == 1:
            await asyncio.sleep(5)
        return TargetResult(output={"label": "a"})

    loaded = suite_for(tmp_path, 3)
    result = run_suite(loaded, opts(tmp_path, target=target, case_timeout_s=0.2, retries=0))
    by_id = {c.id: c for c in result.report.cases}
    assert by_id["r-0001"].error == "timeout"
    assert by_id["r-0001"].scores == {"acc": 0.0}
    assert by_id["r-0001"].passed is False
    assert by_id["r-0000"].scores == {"acc": 1.0}
    assert result.report.metrics["acc"].value == pytest.approx(2 / 3)


def test_failing_case_never_aborts_and_degraded_health(tmp_path: Path) -> None:
    async def target(case_input: dict[str, Any]) -> TargetResult:
        if case_input["i"] % 4 != 0:
            raise TargetError("http 400")
        return TargetResult(output={"label": "a"})

    loaded = suite_for(tmp_path, 8)
    result = run_suite(loaded, opts(tmp_path, target=target, retries=0))
    ext = result.report.extensions or {}
    assert ext["run_health"] == "degraded"
    assert ext["error_rate"] == 0.75
    assert sum(1 for c in result.report.cases if c.error) == 6


def test_retries_then_success_records_attempts(tmp_path: Path) -> None:
    calls: dict[int, int] = {}

    async def target(case_input: dict[str, Any]) -> TargetResult:
        calls[case_input["i"]] = calls.get(case_input["i"], 0) + 1
        if calls[case_input["i"]] < 3:
            raise RetriableTargetError("http 503")
        return TargetResult(output={"label": "a"})

    async def no_sleep(_: float) -> None:
        return None

    result = asyncio.run(call_with_retries(target, {"i": 7}, retries=2, timeout_s=1, sleep=no_sleep))
    assert result[1] == 3
    with pytest.raises(CaseFailure) as info:
        asyncio.run(call_with_retries(target, {"i": 8}, retries=1, timeout_s=1, sleep=no_sleep))
    assert info.value.attempts == 2
    assert info.value.error == "http 503"


def test_backoff_full_jitter_capped() -> None:
    rng = random.Random(0)
    for attempt in range(10):
        delay = backoff_delay(attempt, rng)
        assert 0 <= delay <= min(8.0, 0.5 * 2**attempt)


def test_sync_python_target_runs_in_thread(tmp_path: Path) -> None:
    loaded = suite_for(tmp_path, 5)
    result = run_suite(loaded, opts(tmp_path))
    assert result.report.n_cases == 5
    assert result.report.metrics["acc"].value == 0.0  # echo returns no label


def test_report_deterministic_except_ids_and_latency(tmp_path: Path) -> None:
    loaded = suite_for(tmp_path, 10)
    a = run_suite(loaded, opts(tmp_path)).report.model_dump()
    b = run_suite(loaded, opts(tmp_path)).report.model_dump()
    for r in (a, b):
        for key in ("run_id", "created_at", "latency_p50_ms", "latency_p95_ms"):
            r.pop(key)
        for c in r["cases"]:
            c.pop("latency_ms")
    assert a == b


def test_resume_skips_stored_cases(tmp_path: Path) -> None:
    seen: list[int] = []

    async def target(case_input: dict[str, Any]) -> TargetResult:
        seen.append(case_input["i"])
        return TargetResult(output={"label": "a"})

    loaded = suite_for(tmp_path, 4)
    first = run_suite(loaded, RunOptions(split="test", home=tmp_path / "home", target=target, resamples=100))
    seen.clear()
    resumed = run_suite(
        loaded,
        RunOptions(split="test", home=tmp_path / "home", target=target, resume=first.report.run_id, resamples=100),
    )
    assert seen == []
    assert resumed.report.run_id == first.report.run_id
    assert resumed.report.n_cases == 4


def test_store_down_report_still_written(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    (home / "runs.duckdb").write_text("not a duckdb file")
    loaded = suite_for(tmp_path, 3)
    result = run_suite(loaded, RunOptions(split="test", home=home, resamples=100))
    assert result.store_error is not None
    assert result.report.n_cases == 3


def test_failing_case_is_not_a_metric_error(tmp_path: Path) -> None:
    """Regression (M2 review): an ordinary failing case must not count as a metric error in the gate."""
    from evalgate.stats.gate import check

    async def target(case_input: dict[str, Any]) -> TargetResult:
        return TargetResult(output={"total": "n/a" if case_input["i"] == 0 else 1.0})

    metrics = [
        {
            "name": "tot",
            "kind": "numeric_tolerance",
            "threshold": 0.9,
            "params": {"actual": "output.total", "expected": 1.0},
        }
    ]
    loaded = suite_for(tmp_path, 20, metrics=metrics)
    report = run_suite(loaded, opts(tmp_path, target=target)).report
    assert report.metrics["tot"].value == 0.95
    assert (report.extensions or {})["metric_errors"] == {}
    assert check(report, report_sha256="x").passed


def test_crashing_metric_is_a_metric_error(tmp_path: Path) -> None:
    import evalgate
    from evalgate.metrics.registry import unregister
    from evalgate.stats.gate import check

    @evalgate.metric("crash")
    def crash(c, r):  # type: ignore[no-untyped-def]
        raise ZeroDivisionError("boom")

    try:
        loaded = suite_for(tmp_path, 3, metrics=[{"name": "c", "kind": "custom", "params": {"metric": "crash"}}])
        report = run_suite(loaded, opts(tmp_path)).report
        assert (report.extensions or {})["metric_errors"] == {"c": 3}
        assert [f.reason for f in check(report, report_sha256="x").failures] == ["error"]
    finally:
        unregister("crash")


def test_failed_cases_score_the_worst_value_for_lower_metrics(tmp_path: Path) -> None:
    """A crash must never improve a lower-is-better metric: errored cases score 1.0 there, 0.0 for higher."""
    lower = {
        "name": "wrong",
        "kind": "exact",
        "params": {"actual": "output.label", "expected": "expected.label"},
        "threshold": 0.6,
        "direction": "lower",
        "gate": True,
    }
    higher = {**lower, "name": "acc", "direction": "higher", "threshold": 0.5}

    async def target(case_input: dict[str, Any]) -> TargetResult:
        if case_input["i"] % 2:
            raise TargetError("down")
        return TargetResult(output={"label": "a"})  # exact match: 1.0 on both metrics

    loaded = suite_for(tmp_path, 10, metrics=[lower, higher])
    report = run_suite(loaded, opts(tmp_path, target=target)).report
    errored = [c for c in report.cases if c.error]
    assert len(errored) == 5
    assert all(c.scores == {"wrong": 1.0, "acc": 0.0} for c in errored)
    assert report.metrics["wrong"].value == 1.0  # healthy cases also score 1.0 (match), errors cannot lower it
    assert report.metrics["acc"].value == 0.5


def test_resume_reruns_errored_cases_and_ignores_other_splits(tmp_path: Path) -> None:
    calls: list[int] = []
    fail = {1}

    async def target(case_input: dict[str, Any]) -> TargetResult:
        calls.append(case_input["i"])
        if case_input["i"] in fail:
            raise TargetError("down")
        return TargetResult(output={"label": "a"})

    loaded = suite_for(tmp_path, 4)
    first = run_suite(loaded, RunOptions(split="test", home=tmp_path / "home", target=target, resamples=100))
    assert sum(1 for c in first.report.cases if c.error) == 1
    calls.clear()
    fail.clear()
    resumed = run_suite(
        loaded,
        RunOptions(split="test", home=tmp_path / "home", target=target, resume=first.report.run_id, resamples=100),
    )
    assert calls == [1]  # only the errored case runs again
    assert not any(c.error for c in resumed.report.cases)
    assert resumed.report.metrics["acc"].value == 1.0

    other = load_suite(write_suite(tmp_path / "s2.yaml", write_dataset(tmp_path / "d2.jsonl", rows(2))), split="test")
    again = run_suite(
        other,
        RunOptions(split="test", home=tmp_path / "home", target=target, resume=first.report.run_id, resamples=100),
    )
    assert again.report.n_cases == 2  # stored cases outside the current dataset are not reported


def test_resume_rejects_a_malformed_run_id(tmp_path: Path) -> None:
    from evalgate.errors import InvalidInputError

    with pytest.raises(InvalidInputError, match="run id"):
        run_suite(suite_for(tmp_path, 2), opts(tmp_path, resume="../../etc"))


def test_empty_split_is_invalid_input(tmp_path: Path) -> None:
    from evalgate.errors import InvalidInputError

    data = write_dataset(tmp_path / "d.jsonl", rows(3, split="dev"))
    with pytest.raises(InvalidInputError, match="no cases"):
        load_suite(write_suite(tmp_path / "s.yaml", data), split="test")


def test_gate_fails_closed_on_a_report_without_cases() -> None:
    from evalgate.stats.gate import check
    from tests.factories import make_report

    report = make_report({"acc": [1.0]}).model_copy(update={"cases": [], "n_cases": 0})
    result = check(report, report_sha256="x", resamples=10)
    assert not result.passed
    assert [(f.metric, f.reason) for f in result.failures] == [("n_cases", "error")]
