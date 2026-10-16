"""Performance and determinism budgets (NFR-1 to NFR-9). Writes evals/reports/bench.json; exit 1 on any miss.

NFR-1 200 cases, concurrency 16, 200 ms target: < 300 s.   NFR-2 engine overhead per case p95 < 5 ms.
NFR-3 cached re-run of 200 judged cases < 10 s.             NFR-4 live CI estimate < USD 1.00.
NFR-5 offline run opens no non-loopback socket.             NFR-6 ``import evalgate`` median < 300 ms.
NFR-7 wheel < 1 MB.                                         NFR-8 viewer run detail p95 < 200 ms (200 cases),
                                                            comparison 200 cases x 10,000 resamples < 2 s.
NFR-9 same inputs and seed give identical reports except run_id, created_at and latencies.
"""

from __future__ import annotations

import ipaddress
import json
import socket
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from evalgate.budget import estimate_judge_cost  # noqa: E402
from evalgate.config import judge_model  # noqa: E402
from evalgate.report.build import write_report  # noqa: E402
from evalgate.runner import RunOptions, run_suite  # noqa: E402
from evalgate.runner.engine import Runner  # noqa: E402
from evalgate.suite import load_suite  # noqa: E402

RESULTS: list[dict[str, Any]] = []


def record(nfr: str, what: str, value: float, budget: float, unit: str, ok: bool | None = None) -> None:
    passed = value < budget if ok is None else ok
    RESULTS.append(
        {"nfr": nfr, "what": what, "value": round(value, 4), "budget": budget, "unit": unit, "passed": passed}
    )
    print(f"{nfr:6} {what:58} {value:10.3f} {unit:4} (budget {budget}) {'ok' if passed else 'MISS'}")


def suite(tmp: Path, name: str, n: int, target: str, concurrency: int, judge: bool = False) -> Path:
    rows = [
        {
            "id": f"b-{i:04d}",
            "split": "test",
            "input": {"answer": f"Refunds within {i % 30 + 1} days."},
            "expected": {"answer": f"Refunds within {i % 30 + 1} days.", "label": "a"},
        }
        for i in range(n)
    ]
    data = tmp / f"{name}.jsonl"
    data.write_text("".join(json.dumps(r) + "\n" for r in rows))
    metrics: list[dict[str, Any]] = [
        {
            "name": "acc",
            "kind": "exact",
            "threshold": 0.5,
            "params": {"actual": "output.label", "expected": "expected.label"},
        }
    ]
    if judge:
        metrics.append(
            {
                "name": "judge",
                "kind": "judge",
                "threshold": 0.5,
                "params": {"rubric": str(ROOT / "evals/rubrics/answer_correctness.v1.yaml"), "input": "input.answer"},
            }
        )
    spec = {
        "schema": "evalgate.suite.v1",
        "name": name,
        "dataset": str(data),
        "target": {"python": target},
        "concurrency": concurrency,
        "metrics": metrics,
        "splits": ["test"],
    }
    path = tmp / f"{name}.yaml"
    path.write_text(yaml.safe_dump(spec))
    return path


def nfr1(tmp: Path) -> None:
    loaded = load_suite(suite(tmp, "nfr1", 200, "tests.fixtures.bench_targets:sleepy", 16), split="test")
    start = time.perf_counter()
    run_suite(loaded, RunOptions(split="test", home=tmp / "h1", use_store=False))
    record("NFR-1", "200 cases, concurrency 16, 200 ms target", time.perf_counter() - start, 300, "s")


def nfr2(tmp: Path) -> None:
    loaded = load_suite(suite(tmp, "nfr2", 1000, "tests.fixtures.bench_targets:noop", 1), split="test")
    durations: list[float] = []
    original = Runner.run_case

    async def timed(self: Runner, target: Any, metrics: Any, case: Any, sem: Any) -> Any:
        start = time.perf_counter()
        out = await original(self, target, metrics, case, sem)
        durations.append((time.perf_counter() - start) * 1000)
        return out

    Runner.run_case = timed  # type: ignore[method-assign]
    try:
        run_suite(loaded, RunOptions(split="test", home=tmp / "h2", use_store=False, cache_mode="off"))
    finally:
        Runner.run_case = original  # type: ignore[method-assign]
    p95 = statistics.quantiles(durations, n=100)[94]
    record("NFR-2", "engine overhead per case p95 (1,000 no-op cases)", p95, 5, "ms")


def nfr3(tmp: Path) -> None:
    loaded = load_suite(suite(tmp, "nfr3", 200, "tests.fixtures.bench_targets:noop", 16, judge=True), split="test")
    home = tmp / "h3"
    run_suite(loaded, RunOptions(split="test", home=home, use_store=False))
    start = time.perf_counter()
    report = run_suite(loaded, RunOptions(split="test", home=home, use_store=False)).report
    elapsed = time.perf_counter() - start
    ext = report.extensions or {}
    record(
        "NFR-3",
        "cached re-run of 200 judged cases",
        elapsed,
        10,
        "s",
        ok=elapsed < 10 and ext.get("provider_calls") == 0,
    )


def nfr4() -> None:
    estimate = estimate_judge_cost(60, [(judge_model(), 2)], budget_usd=1.0)  # the answer suite on test, live
    record("NFR-4", f"live CI estimate ({estimate.calls} {judge_model()} judge calls)", estimate.cost_usd, 1.0, "USD")


def nfr5(tmp: Path) -> None:
    seen: list[Any] = []
    real = socket.socket.connect

    def connect(self: socket.socket, address: Any) -> Any:
        seen.append(address)
        return real(self, address)

    socket.socket.connect = connect  # type: ignore[method-assign]
    try:
        loaded = load_suite(suite(tmp, "nfr5", 50, "tests.fixtures.bench_targets:noop", 8, judge=True), split="test")
        run_suite(loaded, RunOptions(split="test", home=tmp / "h5"))
    finally:
        socket.socket.connect = real  # type: ignore[method-assign]

    def loopback(addr: Any) -> bool:
        try:
            return ipaddress.ip_address(str(addr[0])).is_loopback
        except ValueError:
            return addr[0] == "localhost"

    external = [a for a in seen if isinstance(a, tuple) and not loopback(a)]
    record("NFR-5", "non-loopback connections during an offline judged run", len(external), 1, "n")


def nfr6() -> None:
    times = []
    for _ in range(5):
        out = subprocess.run(
            [sys.executable, "-c", "import time; t=time.perf_counter(); import evalgate; print(time.perf_counter()-t)"],
            capture_output=True,
            text=True,
            check=True,
        )
        times.append(float(out.stdout.strip()) * 1000)
    record("NFR-6", "import evalgate, median of 5 fresh interpreters", statistics.median(times), 300, "ms")


def nfr7() -> None:
    wheels = sorted((ROOT / "dist").glob("evalgate-*.whl"))
    if not wheels:
        subprocess.run(
            ["uv", "build", "--package", "evalgate", "--wheel", "--out-dir", str(ROOT / "dist")],
            cwd=ROOT,
            capture_output=True,
            check=True,
        )
        wheels = sorted((ROOT / "dist").glob("evalgate-*.whl"))
    record("NFR-7", f"wheel size ({wheels[-1].name})", wheels[-1].stat().st_size / 1_000_000, 1.0, "MB")


def nfr8(tmp: Path) -> None:
    import httpx
    from tests.factories import make_report
    from tests.viewer_helpers import viewer

    from evalgate.stats.gate import check

    reports = tmp / "reports"
    reports.mkdir()
    base = make_report({"acc": [1.0] * 200, "fmt": [1.0] * 200}, threshold=0.9)
    cand = make_report({"acc": [0.0] * 15 + [1.0] * 185, "fmt": [1.0] * 200}, threshold=0.9)
    base = base.model_copy(update={"run_id": "0000000a-0000-7000-8000-000000000001"})
    cand = cand.model_copy(update={"run_id": "0000000b-0000-7000-8000-000000000002"})
    write_report(base, reports / "base.json")
    write_report(cand, reports / "cand.json")
    with viewer(reports) as url, httpx.Client() as client:
        client.get(f"{url}/runs/{cand.run_id}")  # warm templates
        samples = []
        for _ in range(40):
            start = time.perf_counter()
            assert client.get(f"{url}/runs/{cand.run_id}").status_code == 200
            samples.append((time.perf_counter() - start) * 1000)
            time.sleep(0.03)  # stay under the 50 requests/s rate limit
    record("NFR-8", "viewer run detail p95, 200 cases", statistics.quantiles(samples, n=100)[94], 200, "ms")
    start = time.perf_counter()
    check(cand, report_sha256="bench", baseline=base, resamples=10_000)
    record("NFR-8", "comparison, 200 cases x 10,000 resamples (2 metrics)", time.perf_counter() - start, 2, "s")


def nfr9(tmp: Path) -> None:
    loaded = load_suite(suite(tmp, "nfr9", 60, "tests.fixtures.bench_targets:noop", 8, judge=True), split="test")
    dumps = []
    for i in range(2):
        report = run_suite(loaded, RunOptions(split="test", home=tmp / f"h9-{i}", use_store=False)).report.model_dump()
        for key in ("run_id", "created_at", "latency_p50_ms", "latency_p95_ms"):
            report.pop(key)
        for case in report["cases"]:
            case.pop("latency_ms")
        dumps.append(json.dumps(report, sort_keys=True))
    record("NFR-9", "identical reports except run_id, created_at, latencies", float(dumps[0] != dumps[1]), 1, "diff")


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp = Path(tmp_dir)
        nfr1(tmp)
        nfr2(tmp)
        nfr3(tmp)
        nfr4()
        nfr5(tmp)
        nfr6()
        nfr7()
        nfr8(tmp)
        nfr9(tmp)
    out = ROOT / "evals" / "reports" / "bench.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    passed = all(r["passed"] for r in RESULTS)
    out.write_text(
        json.dumps(
            {
                "schema": "evalgate.bench.v1",
                "command": "make bench",
                "passed": passed,
                "python": sys.version.split()[0],
                "results": RESULTS,
            },
            indent=2,
        )
        + "\n"
    )
    print(f"bench: {'all budgets met' if passed else 'budget MISSED'}; wrote {out.relative_to(ROOT)}")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
