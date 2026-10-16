"""Read-only report viewer: stdlib ``ThreadingHTTPServer`` + Jinja2 (FR-8).

Routes: ``/`` runs list (``?suite=``, ``?mode=``), ``/runs/{run_id}`` (``?status=failed``, ``?tag=``),
``/compare?base=&cand=`` (computed in a background thread; the page shows a loading state until done),
``/api/runs``, ``/api/runs/{run_id}``, ``/static/{file}``, ``/healthz``.
Security: binds 127.0.0.1 by default, bearer token when ``EVALGATE_SERVE_TOKEN`` is set, run ids must match
``^[0-9a-f-]{36}$``, reads stay inside the reports directory, 50 requests/s per client, reports over
50 MB are refused (413), autoescaped templates and a strict Content-Security-Policy.
"""

from __future__ import annotations

import hmac
import json
import re
import socket
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urlsplit

from jinja2 import Environment, PackageLoader, select_autoescape
from pydantic import ValidationError

from evalgate import __version__, config
from evalgate.contracts import CheckResult, Report
from evalgate.ids import RUN_ID_PATTERN
from evalgate.suite.limits import MAX_REPORT_BYTES

RUN_ID = re.compile(RUN_ID_PATTERN)
STATIC_FILES = {"tokens.css": "text/css", "app.css": "text/css", "app.js": "text/javascript"}
RATE_LIMIT_PER_S = 50
CSP = (
    "default-src 'none'; style-src 'self'; script-src 'self'; img-src 'self' data:; "
    "form-action 'self'; base-uri 'none'; frame-ancestors 'none'"
)


@dataclass
class Entry:
    path: Path
    report: Report | None = None
    error: str | None = None
    status: int = 200


@dataclass
class ReportIndex:
    root: Path
    _cache: dict[Path, tuple[float, int, Entry]] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def scan(self) -> list[Entry]:
        entries = []
        files = sorted(p for p in self.root.rglob("*.json") if p.is_file()) if self.root.is_dir() else []
        with self._lock:
            for path in files:
                if not path.resolve().is_relative_to(self.root.resolve()):
                    continue  # never follow a symlink out of the reports directory
                try:
                    stat = path.stat()
                except OSError:
                    continue  # deleted between listing and stat
                cached = self._cache.get(path)
                if cached and cached[0] == stat.st_mtime and cached[1] == stat.st_size:
                    entries.append(cached[2])
                    continue
                entry = self._load(path, stat.st_size)
                self._cache[path] = (stat.st_mtime, stat.st_size, entry)
                entries.append(entry)
        return entries

    def _load(self, path: Path, size: int) -> Entry:
        rel = path.relative_to(self.root)
        if size > MAX_REPORT_BYTES:
            return Entry(path, error=f"{rel}: report is {size} bytes, over the 50 MB limit", status=413)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, RecursionError, OSError) as exc:  # ValueError covers JSON and Unicode errors
            return Entry(path, error=f"{rel}: invalid JSON: {exc.__class__.__name__}: {str(exc)[:200]}")
        if not isinstance(data, dict) or not str(data.get("schema", "")).startswith("evalgate.report"):
            return Entry(path, error=f"{rel}: not an evalgate report (missing schema evalgate.report.v1)")
        try:
            return Entry(path, report=Report.model_validate(data))
        except RecursionError:
            return Entry(path, error=f"{rel}: report is nested too deeply")
        except ValidationError as exc:
            first = exc.errors()[0]
            where = "$" + "".join(f"[{p}]" if isinstance(p, int) else f".{p}" for p in first["loc"])
            return Entry(path, error=f"{rel}: {where}: {first['msg']}")

    def reports(self) -> tuple[list[Report], list[Entry]]:
        entries = self.scan()
        good = [e.report for e in entries if e.report is not None]
        bad = [e for e in entries if e.report is None]
        good.sort(key=lambda r: r.created_at, reverse=True)
        return good, bad

    def find(self, run_id: str) -> Entry | None:
        for entry in self.scan():
            if entry.report is not None and entry.report.run_id == run_id:
                return entry
        return None


class CompareJobs:
    """Comparisons run in a background thread; pages poll until the result exists."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.jobs: dict[tuple[str, str], dict[str, Any]] = {}

    def get_or_start(self, base: Report, cand: Report) -> dict[str, Any]:
        key = (base.run_id, cand.run_id)
        with self.lock:
            job = self.jobs.get(key)
            if job is None or job.get("signature") != (base.created_at, cand.created_at):
                if len(self.jobs) >= 128:  # bounded memory: forget the oldest comparison
                    self.jobs.pop(next(iter(self.jobs)))
                job = {"status": "running", "signature": (base.created_at, cand.created_at), "started": time.time()}
                self.jobs[key] = job
                threading.Thread(target=self._run, args=(job, base, cand), daemon=True).start()
                return dict(job)
            return dict(job)

    @staticmethod
    def _run(job: dict[str, Any], base: Report, cand: Report) -> None:
        from evalgate.stats.gate import check

        try:
            result = check(
                cand, report_sha256="viewer", baseline=base, max_regression_pp=1.0, seed=config.bootstrap_seed()
            )
            job.update(status="done", result=result, seconds=round(time.time() - job["started"], 3))
        except Exception as exc:  # shown in the error state
            job.update(status="error", error=f"{exc.__class__.__name__}: {exc}")


class RateLimiter:
    def __init__(self, per_second: int = RATE_LIMIT_PER_S) -> None:
        self.per_second = per_second
        self.hits: dict[str, deque[float]] = defaultdict(deque)
        self.lock = threading.Lock()

    def allow(self, client: str) -> bool:
        now = time.monotonic()
        with self.lock:
            q = self.hits[client]
            while q and now - q[0] > 1.0:
                q.popleft()
            if len(self.hits) > 10_000:  # bounded memory: drop idle clients
                for key in [k for k, v in self.hits.items() if not v or now - v[-1] > 1.0]:
                    del self.hits[key]
                q = self.hits[client]
            if len(q) >= self.per_second:
                return False
            q.append(now)
            return True


def gate_status(report: Report) -> dict[str, Any]:
    """Pass/fail without a baseline (thresholds, budgets, run health)."""
    from evalgate.stats.gate import check

    result = check(report, report_sha256="viewer", seed=config.bootstrap_seed(), resamples=1)
    return {"passed": result.passed, "reasons": sorted({f.reason for f in result.failures})}


class Viewer:
    def __init__(self, reports_dir: Path, token: str | None = None) -> None:
        self.root = reports_dir.resolve()
        self.index = ReportIndex(self.root)
        self.jobs = CompareJobs()
        self.limiter = RateLimiter()
        self.token = config.serve_token() if token is None else token
        self.allowed_hosts = {"localhost", "127.0.0.1", "::1"} | config.serve_allowed_hosts()
        self.env = Environment(
            loader=PackageLoader("evalgate.viewer", "templates"),
            autoescape=select_autoescape(["html", "j2"]),
            trim_blocks=True,
            lstrip_blocks=True,
        )
        self.env.globals.update(version=__version__, qs=urlencode)


class Handler(BaseHTTPRequestHandler):
    timeout = 30  # seconds a slow client may hold a worker thread
    server_version = "evalgate-viewer"
    sys_version = ""
    viewer: Viewer

    def log_message(self, fmt: str, *args: Any) -> None:  # quiet by default
        return

    # plumbing ----------------------------------------------------------------------------------
    def send(self, status: int, body: bytes, content_type: str, extra: dict[str, str] | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cache-Control", "no-store")
        if content_type.startswith("text/html"):
            self.send_header("Content-Security-Policy", CSP)
            self.send_header("X-Frame-Options", "DENY")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def html(self, template: str, status: int = 200, **ctx: Any) -> None:
        theme = self.query.get("theme", [""])[0]
        ctx.setdefault("theme", theme if theme in ("light", "dark") else None)
        body = self.viewer.env.get_template(template).render(**ctx).encode("utf-8")
        self.send(status, body, "text/html; charset=utf-8")

    def json_body(self, payload: Any, status: int = 200) -> None:
        self.send(status, json.dumps(payload, default=str).encode("utf-8"), "application/json")

    def error_page(self, status: int, title: str, detail: str) -> None:
        if self.path_only.startswith("/api/"):
            self.json_body({"error": title, "detail": detail}, status)
        else:
            self.html("error.html", status=status, title=title, detail=detail, status_code=status)

    def host_allowed(self) -> bool:
        """Reject foreign Host headers (DNS rebinding against a loopback viewer)."""
        host = (self.headers.get("Host") or "").strip().lower()
        if host.startswith("["):
            name = host[1 : host.find("]")] if "]" in host else host
        else:
            name = host.rsplit(":", 1)[0] if host.count(":") == 1 else host
        return name in self.viewer.allowed_hosts

    def authorized(self) -> bool:
        if not self.viewer.token:
            return True
        header = self.headers.get("Authorization", "")
        supplied = header.removeprefix("Bearer ").strip() if header.startswith("Bearer ") else ""
        return hmac.compare_digest(supplied.encode(), self.viewer.token.encode())

    # routing -----------------------------------------------------------------------------------
    def do_HEAD(self) -> None:
        self.do_GET()

    def do_GET(self) -> None:
        parts = urlsplit(self.path)
        self.path_only = parts.path
        self.query = parse_qs(parts.query, keep_blank_values=False)
        if not self.host_allowed():
            self.send(421, b"Unexpected Host header", "text/plain; charset=utf-8")
            return
        if self.path_only == "/healthz":
            self.json_body({"status": "ok", "version": __version__})
            return
        if not self.viewer.limiter.allow(self.client_address[0]):
            self.send(429, b"Too many requests", "text/plain; charset=utf-8", {"Retry-After": "1"})
            return
        if not self.authorized():
            self.send(
                401,
                b"Bearer token required",
                "text/plain; charset=utf-8",
                {"WWW-Authenticate": 'Bearer realm="evalgate"'},
            )
            return
        try:
            self.route()
        except BrokenPipeError:
            return
        except Exception as exc:  # never leak a traceback
            self.error_page(500, "Internal error", exc.__class__.__name__)

    def do_POST(self) -> None:
        self.send(405, b"The viewer is read-only", "text/plain; charset=utf-8", {"Allow": "GET, HEAD"})

    do_PUT = do_DELETE = do_PATCH = do_POST

    def route(self) -> None:
        path = self.path_only
        if path == "/":
            return self.runs_page()
        if path == "/compare":
            return self.compare_page()
        if path == "/api/runs":
            return self.api_runs()
        m = re.fullmatch(r"/runs/([^/]+)", path)
        if m:
            return self.run_page(m.group(1))
        m = re.fullmatch(r"/api/runs/([^/]+)", path)
        if m:
            return self.api_run(m.group(1))
        m = re.fullmatch(r"/static/([^/]+)", path)
        if m:
            return self.static(m.group(1))
        return self.error_page(404, "Not found", f"No page at {path}.")

    # pages -------------------------------------------------------------------------------------
    def _filtered(self) -> tuple[list[Report], list[Entry], dict[str, str]]:
        reports, bad = self.viewer.index.reports()
        filters = {k: self.query.get(k, [""])[0] for k in ("suite", "mode")}
        if filters["mode"] and filters["mode"] not in ("offline", "live"):
            raise ValueError("mode must be offline or live")
        if filters["suite"]:
            reports = [r for r in reports if r.suite == filters["suite"]]
        if filters["mode"]:
            reports = [r for r in reports if r.mode == filters["mode"]]
        return reports, bad, filters

    def runs_page(self) -> None:
        try:
            reports, bad, filters = self._filtered()
        except ValueError as exc:
            return self.error_page(400, "Bad request", str(exc))
        all_reports, _ = self.viewer.index.reports()
        rows = [{"r": r, "gate": gate_status(r), "split": (r.extensions or {}).get("split") or "n/a"} for r in reports]
        self.html(
            "runs.html",
            rows=rows,
            bad=bad,
            filters=filters,
            suites=sorted({r.suite for r in all_reports}),
            all_reports=all_reports,
            reports_dir=str(self.viewer.root),
        )

    def run_page(self, run_id: str) -> None:
        if not RUN_ID.fullmatch(run_id):
            return self.error_page(400, "Bad request", "Run ids are 36 characters of 0-9, a-f and '-'.")
        entry = self.viewer.index.find(run_id)
        if entry is None or entry.report is None:
            return self.error_page(404, "Run not found", f"No report with run id {run_id}.")
        r = entry.report
        status = self.query.get("status", [""])[0]
        tag = self.query.get("tag", [""])[0]
        if status not in ("", "failed", "passed"):
            return self.error_page(400, "Bad request", "status must be failed or passed")
        ext = r.extensions or {}
        tags: dict[str, list[str]] = ext.get("case_tags") or {}
        cases = r.cases
        if status:
            cases = [c for c in cases if c.passed == (status == "passed")]
        if tag:
            cases = [c for c in cases if tag in tags.get(c.id, [])]
        cases = sorted(cases, key=lambda c: (c.passed, c.id))
        self.html(
            "run.html",
            r=r,
            ext=ext,
            cases=cases,
            status_filter=status,
            tag=tag,
            gate=gate_status(r),
            all_tags=sorted({t for ts in tags.values() for t in ts}),
            judge=ext.get("judge") or {},
            judge_details=ext.get("judge_details") or {},
            gates=ext.get("gates") or {},
        )

    def compare_page(self) -> None:
        base_id, cand_id = self.query.get("base", [""])[0], self.query.get("cand", [""])[0]
        reports, _ = self.viewer.index.reports()
        if not base_id or not cand_id:
            return self.html("compare.html", state="pick", reports=reports, base=None, cand=None)
        if not (RUN_ID.fullmatch(base_id) and RUN_ID.fullmatch(cand_id)):
            return self.error_page(400, "Bad request", "base and cand must be run ids.")
        base_e, cand_e = self.viewer.index.find(base_id), self.viewer.index.find(cand_id)
        if base_e is None or cand_e is None or base_e.report is None or cand_e.report is None:
            return self.error_page(404, "Run not found", "One of the runs to compare does not exist.")
        base, cand = base_e.report, cand_e.report
        job = self.viewer.jobs.get_or_start(base, cand)
        if job["status"] == "running":
            return self.html("compare.html", state="loading", base=base, cand=cand, reports=reports)
        if job["status"] == "error":
            return self.html(
                "compare.html", state="error", base=base, cand=cand, error=job["error"], reports=reports, status=500
            )
        result: CheckResult = job["result"]
        failures: dict[str, Any] = {}
        for f in result.failures:  # regressions win the badge; every reason is listed
            if f.metric not in failures or f.reason == "regression":
                failures[f.metric] = f
        base_scores = {c.id: c.scores for c in base.cases}
        moved: list[dict[str, Any]] = []
        for c in cand.cases:
            before = base_scores.get(c.id)
            if before is None:
                continue
            # Positive is better: lower-is-better metrics count with the sign flipped.
            delta = sum(
                (c.scores.get(k, 0.0) - v)
                * (-1.0 if k in cand.metrics and cand.metrics[k].direction == "lower" else 1.0)
                for k, v in before.items()
            )
            if delta != 0:
                moved.append({"case": c, "before": before, "delta": delta})
        moved.sort(key=lambda x: (float(x["delta"]), str(x["case"].id)))
        self.html(
            "compare.html",
            state="done",
            base=base,
            cand=cand,
            result=result,
            failures=failures,
            moved=moved,
            reports=reports,
            seconds=job.get("seconds"),
        )

    # api ---------------------------------------------------------------------------------------
    def api_runs(self) -> None:
        try:
            reports, bad, _ = self._filtered()
        except ValueError as exc:
            return self.error_page(400, "Bad request", str(exc))
        self.json_body(
            {
                "runs": [
                    {
                        "run_id": r.run_id,
                        "suite": r.suite,
                        "mode": r.mode,
                        "created_at": r.created_at,
                        "n_cases": r.n_cases,
                        "cost_usd_total": r.cost_usd_total,
                        "latency_p95_ms": r.latency_p95_ms,
                        "passed": gate_status(r)["passed"],
                    }
                    for r in reports
                ],
                "errors": [
                    {"file": str(e.path.relative_to(self.viewer.root)), "error": e.error, "status": e.status}
                    for e in bad
                ],
            }
        )

    def api_run(self, run_id: str) -> None:
        if not RUN_ID.fullmatch(run_id):
            return self.error_page(400, "Bad request", "invalid run id")
        entry = self.viewer.index.find(run_id)
        if entry is None or entry.report is None:
            return self.error_page(404, "Not found", f"no run {run_id}")
        self.json_body(entry.report.model_dump(mode="json", by_alias=True))

    def static(self, name: str) -> None:
        if name not in STATIC_FILES:
            return self.error_page(404, "Not found", "No such static file.")
        body = resources.files("evalgate.viewer").joinpath("static").joinpath(name).read_bytes()
        self.send(200, body, f"{STATIC_FILES[name]}; charset=utf-8")


class _ThreadingHTTPServerV6(ThreadingHTTPServer):
    address_family = socket.AF_INET6


def server_class_for(host: str) -> type[ThreadingHTTPServer]:
    return _ThreadingHTTPServerV6 if ":" in host else ThreadingHTTPServer


def make_server(
    reports_dir: Path, host: str = "127.0.0.1", port: int = 8100, token: str | None = None
) -> ThreadingHTTPServer:
    viewer = Viewer(Path(reports_dir), token=token)
    handler = type("BoundHandler", (Handler,), {"viewer": viewer})
    server = server_class_for(host)((host, port), handler)
    server.daemon_threads = True
    return server


def serve(reports_dir: Path, host: str = "127.0.0.1", port: int = 8100) -> None:
    if host not in ("127.0.0.1", "localhost", "::1") and not config.serve_token():
        print("evalgate: warning: serving on a non-loopback address without EVALGATE_SERVE_TOKEN", flush=True)
    server = make_server(reports_dir, host=host, port=port)
    print(
        f"evalgate viewer on http://{host}:{server.server_address[1]} serving {Path(reports_dir).resolve()}", flush=True
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:  # pragma: no cover
        pass
    finally:
        server.server_close()
