"""Start the viewer on a random loopback port for tests."""

from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from evalgate.viewer.server import make_server


@contextmanager
def viewer(reports_dir: Path, token: str = "") -> Iterator[str]:
    server = make_server(reports_dir, host="127.0.0.1", port=0, token=token)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()
