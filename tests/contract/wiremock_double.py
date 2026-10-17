"""A WireMock-compatible double for contract tests.

Tests talk to WireMock through its HTTP API only: stub mappings from ``deploy/wiremock/<name>/mappings``,
``GET /__admin/requests`` for the request journal and ``POST /__admin/reset``. When
``WIREMOCK_<NAME>_URL`` is set (``compose.test.yaml`` runs real WireMock on 8142 and 8143) the tests use
it; otherwise this in-process double serves the same mapping files with the subset of WireMock
semantics they use: method, ``url``/``urlPath``/``urlPathPattern``, basic auth, priority, scenarios,
``status``/``jsonBody``/``headers``.
"""

from __future__ import annotations

import base64
import json
import os
import re
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[2]


def load_mappings(name: str) -> list[dict[str, Any]]:
    mappings: list[dict[str, Any]] = []
    for path in sorted((ROOT / "deploy" / "wiremock" / name / "mappings").glob("*.json")):
        data = json.loads(path.read_text())
        mappings.extend(data.get("mappings", [data]))
    return mappings


class Double:
    def __init__(self, mappings: list[dict[str, Any]]) -> None:
        self.mappings = mappings
        self.journal: list[dict[str, Any]] = []
        self.states: dict[str, str] = {}
        self.lock = threading.Lock()

    def reset(self) -> None:
        with self.lock:
            self.journal.clear()
            self.states.clear()

    def matches(self, m: dict[str, Any], method: str, path: str, headers: dict[str, str]) -> bool:
        req = m["request"]
        if req.get("method", "ANY") not in ("ANY", method):
            return False
        url_path = path.split("?", 1)[0]
        if "url" in req and req["url"] != path:
            return False
        if "urlPath" in req and req["urlPath"] != url_path:
            return False
        if "urlPathPattern" in req and not re.fullmatch(req["urlPathPattern"], url_path):
            return False
        creds = req.get("basicAuthCredentials")
        if creds:
            want = "Basic " + base64.b64encode(f"{creds['username']}:{creds['password']}".encode()).decode()
            if headers.get("authorization") != want:
                return False
        scenario = m.get("scenarioName")
        if scenario and "requiredScenarioState" in m:
            return self.states.get(scenario, "Started") == m["requiredScenarioState"]
        return True

    def handle(self, method: str, path: str, headers: dict[str, str], body: str) -> tuple[int, dict[str, str], bytes]:
        if path.startswith("/__admin/requests"):
            if method == "DELETE":
                self.reset()
                return 200, {}, b"{}"
            return 200, {"Content-Type": "application/json"}, json.dumps({"requests": list(self.journal)}).encode()
        if path.startswith("/__admin/reset") or path.startswith("/__admin/scenarios/reset"):
            self.reset()
            return 200, {}, b"{}"
        with self.lock:
            self.journal.append(
                {
                    "request": {
                        "method": method,
                        "url": path,
                        "body": body,
                        "headers": {k: v for k, v in headers.items() if k != "authorization"},
                    }
                }
            )
            candidates = [m for m in self.mappings if self.matches(m, method, path, headers)]
            candidates.sort(key=lambda m: m.get("priority", 5))
            if not candidates:
                return 404, {"Content-Type": "application/json"}, b'{"message": "no stub"}'
            m = candidates[0]
            if m.get("scenarioName") and "newScenarioState" in m:
                self.states[m["scenarioName"]] = m["newScenarioState"]
        resp = m["response"]
        out_headers = dict(resp.get("headers", {}))
        if "jsonBody" in resp:
            out_headers.setdefault("Content-Type", "application/json")
            payload = json.dumps(resp["jsonBody"]).encode()
        else:
            payload = str(resp.get("body", "")).encode()
        return int(resp.get("status", 200)), out_headers, payload


def _handler(double: Double) -> type[BaseHTTPRequestHandler]:
    class H(BaseHTTPRequestHandler):
        def log_message(self, *args: Any) -> None:
            return

        def _do(self) -> None:
            length = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(length).decode() if length else ""
            headers = {k.lower(): v for k, v in self.headers.items()}
            status, out_headers, payload = double.handle(self.command, self.path, headers, body)
            self.send_response(status)
            for k, v in out_headers.items():
                self.send_header(k, v)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        do_GET = do_POST = do_PATCH = do_DELETE = do_PUT = _do

    return H


@contextmanager
def wiremock(name: str) -> Iterator[str]:
    """Yield the base URL of WireMock (real when ``WIREMOCK_<NAME>_URL`` is set, else the double)."""
    real = os.environ.get(f"WIREMOCK_{name.upper()}_URL")
    if real:
        httpx.post(f"{real}/__admin/reset", timeout=10).raise_for_status()
        yield real.rstrip("/")
        return
    double = Double(load_mappings(name))
    server = ThreadingHTTPServer(("127.0.0.1", 0), _handler(double))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()


def received(base_url: str) -> list[dict[str, Any]]:
    """The request journal, oldest first, admin calls excluded."""
    data = httpx.get(f"{base_url}/__admin/requests", timeout=10).json()
    reqs = [r["request"] for r in data["requests"] if not r["request"]["url"].startswith("/__admin")]
    if reqs and "loggedDate" in reqs[0]:
        reqs.sort(key=lambda r: r["loggedDate"])
    return reqs
