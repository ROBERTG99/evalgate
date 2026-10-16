import subprocess
import sys
import time
from pathlib import Path

from evalgate.cache import ResponseCache
from evalgate.llm.gateway import Gateway
from evalgate.runner import RunOptions, run_suite
from evalgate.suite import load_suite
from tests.factories import write_dataset, write_suite


def judged_suite(tmp_path: Path, n: int = 6):  # type: ignore[no-untyped-def]
    rows = [
        {
            "id": f"c-{i}",
            "split": "test",
            "input": {"question": f"q{i}", "answer": f"Within {i} days."},
            "expected": {"answer": f"Within {i} days."},
            "tags": [],
            "meta": {},
        }
        for i in range(n)
    ]
    data = write_dataset(tmp_path / "d.jsonl", rows)
    metrics = [
        {
            "name": "correct",
            "kind": "judge",
            "threshold": 0.8,
            "params": {
                "rubric": "evals/rubrics/answer_correctness.v1.yaml",
                "candidate": "output.answer",
                "reference": "expected.answer",
                "input": "input.question",
            },
        }
    ]
    suite = write_suite(
        tmp_path / "s.yaml", data, metrics=metrics, target={"python": "tests.fixtures.targets:echo_answer"}
    )
    return load_suite(suite, split="test")


def test_rerun_zero_provider_calls(tmp_path: Path) -> None:
    loaded = judged_suite(tmp_path)
    home = tmp_path / "home"
    first = run_suite(loaded, RunOptions(split="test", home=home, gateway=Gateway(provider_name="fake"), resamples=100))
    ext1 = first.report.extensions or {}
    assert ext1["provider_calls"] == 12  # 6 cases x 2 positions
    assert ext1["cache_hits"] == 0
    second = run_suite(
        loaded, RunOptions(split="test", home=home, gateway=Gateway(provider_name="fake"), resamples=100)
    )
    ext2 = second.report.extensions or {}
    assert ext2["provider_calls"] == 0
    assert ext2["cache_hits"] == ext2["judge_calls"] == 12
    assert second.report.metrics["correct"].value == first.report.metrics["correct"].value == 1.0


def test_cache_modes(tmp_path: Path) -> None:
    path = tmp_path / "cache.duckdb"
    rw = ResponseCache(path, "rw")
    rw.put("k", route="judge", model="m", prompt_version="p", request_digest="d", response={"a": 1})
    rw.put("k", route="judge", model="m", prompt_version="p", request_digest="d", response={"a": 2})  # no overwrite
    assert rw.get("k")["response"] == {"a": 1}
    rw.close()
    ro = ResponseCache(path, "ro")
    assert ro.get("k")["response"] == {"a": 1}
    ro.put("k2", route="judge", model="m", prompt_version="p", request_digest="d", response={})
    assert ro.get("k2") is None
    ro.close()
    off = ResponseCache(path, "off")
    assert off.get("k") is None


def test_lock_readonly_fallback(tmp_path: Path) -> None:
    path = tmp_path / "cache.duckdb"
    seed = ResponseCache(path, "rw")
    seed.put("k", route="judge", model="m", prompt_version="p", request_digest="d", response={"a": 1})
    seed.close()
    holder = subprocess.Popen(
        [
            sys.executable,
            "-c",
            f"import duckdb,time; c=duckdb.connect({str(path)!r}); print('locked', flush=True); time.sleep(30)",
        ],
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        assert holder.stdout is not None
        assert holder.stdout.readline().strip() == "locked"
        start = time.monotonic()
        cache = ResponseCache(path, "rw", lock_timeout_s=1.0)
        assert time.monotonic() - start >= 1.0
        assert cache.mode in ("ro", "off")
        assert cache.fallback is not None
        cache.put("x", route="judge", model="m", prompt_version="p", request_digest="d", response={})
        cache.close()
    finally:
        holder.kill()
        holder.wait()


def test_gc_prunes_by_ttl(tmp_path: Path) -> None:
    cache = ResponseCache(tmp_path / "c.duckdb", "rw")
    cache.put("old", route="judge", model="m", prompt_version="p", request_digest="d", response={})
    assert cache.con is not None
    cache.con.execute("UPDATE responses SET created_at = created_at - INTERVAL 100 DAY")
    cache.put("new", route="judge", model="m", prompt_version="p", request_digest="d", response={})
    assert cache.gc(90) == 1
    assert cache.get("old") is None and cache.get("new") is not None
