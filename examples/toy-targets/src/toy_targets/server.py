"""Run the toy targets in a background thread on a random loopback port (tests, meta-eval, benchmarks)."""

from __future__ import annotations

import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager

import uvicorn


@contextmanager
def running(host: str = "127.0.0.1", port: int = 0) -> Iterator[str]:
    from toy_targets.app import create_app

    config = uvicorn.Config(create_app(), host=host, port=port, log_level="error", lifespan="off")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 15
    while not server.started:
        if time.monotonic() > deadline or not thread.is_alive():
            raise RuntimeError("toy targets did not start")
        time.sleep(0.02)
    bound = server.servers[0].sockets[0].getsockname()[1]
    try:
        yield f"http://{host}:{bound}"
    finally:
        server.should_exit = True
        thread.join(timeout=10)
