"""NFR-5: an offline run opens no network connection beyond loopback and resolves no external host."""

import ipaddress
import socket
from pathlib import Path
from typing import Any

import pytest

from evalgate.runner import RunOptions, run_suite
from evalgate.suite import load_suite

ROOT = Path(__file__).resolve().parents[2]


def is_loopback(host: Any) -> bool:
    if host in ("localhost", "", None):
        return True
    try:
        return ipaddress.ip_address(str(host).split("%")[0]).is_loopback
    except ValueError:
        return False


def test_full_offline_run_opens_no_socket(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, toys_url: str) -> None:
    seen: list[Any] = []
    resolved: list[Any] = []
    real_connect = socket.socket.connect
    real_getaddrinfo = socket.getaddrinfo

    def connect(self: socket.socket, address: Any) -> Any:
        seen.append(address)
        return real_connect(self, address)

    def getaddrinfo(host: Any, *args: Any, **kwargs: Any) -> Any:
        resolved.append(host)
        return real_getaddrinfo(host, *args, **kwargs)

    monkeypatch.setattr(socket.socket, "connect", connect)
    monkeypatch.setattr(socket, "getaddrinfo", getaddrinfo)
    monkeypatch.setenv("EVALGATE_TOYS_URL", toys_url)
    monkeypatch.delenv("EVALGATE_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    for suite in ("classify", "extract", "answer"):  # HTTP targets, deterministic metrics, the judge and the cache
        loaded = load_suite(ROOT / f"evals/suites/{suite}.yaml", split="test")
        report = run_suite(loaded, RunOptions(split="test", home=tmp_path)).report
        assert report.mode == "offline"
    inet = [a for a in seen if isinstance(a, tuple)]
    assert inet, "the HTTP target should have connected to the loopback toy server"
    assert all(is_loopback(a[0]) for a in inet), inet
    assert all(is_loopback(h) for h in resolved), resolved


@pytest.mark.filterwarnings("ignore::UserWarning")
def test_socket_guard_is_on_by_default() -> None:
    with pytest.raises(Exception, match="(?i)socket|host"):
        socket.create_connection(("192.0.2.1", 80), timeout=1)  # TEST-NET-1, never routable
