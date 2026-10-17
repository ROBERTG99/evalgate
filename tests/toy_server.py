"""Run the toy targets in a background thread on a random loopback port."""

from toy_targets.server import running as toy_server

__all__ = ["toy_server"]
