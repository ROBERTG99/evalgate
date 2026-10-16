"""Report viewer HTTP server (walking skeleton: /healthz)."""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


class Handler(BaseHTTPRequestHandler):
    server_version = "evalgate"

    def do_GET(self) -> None:
        if self.path == "/healthz":
            body = json.dumps({"status": "ok"}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_error(404)


def serve(reports_dir: Path, host: str = "127.0.0.1", port: int = 8100) -> None:
    httpd = ThreadingHTTPServer((host, port), Handler)
    httpd.serve_forever()
