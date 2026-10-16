import asyncio
from typing import Any

import httpx
import pytest

from evalgate.contracts import HttpTargetSpec
from evalgate.errors import InvalidInputError
from evalgate.runner.retry import CaseFailure, call_with_retries
from evalgate.targets.base import coerce_steps
from evalgate.targets.http import check_allowed, http_target


async def no_sleep(_: float) -> None:
    return None


def client_with(handler: Any) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def test_503_twice_then_ok() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        assert request.headers["X-Toy-Version"] == "v1"
        if calls["n"] <= 2:
            return httpx.Response(503)
        return httpx.Response(
            200,
            json={
                "label": "billing",
                "steps": [
                    {
                        "node": "classify",
                        "kind": "llm",
                        "model": "toy-model",
                        "input_tokens": 10,
                        "output_tokens": 2,
                        "args": {"ignored": True},
                    }
                ],
            },
        )

    async def go() -> Any:
        async with client_with(handler) as client:
            target = http_target(
                HttpTargetSpec(url="http://localhost:8110/classify", headers={"X-Toy-Version": "v1"}), client=client
            )
            return await call_with_retries(target, {"text": "hi"}, retries=2, timeout_s=5, sleep=no_sleep)

    result, attempts = asyncio.run(go())
    assert attempts == 3
    assert result.output["label"] == "billing"
    assert result.steps[0].model == "toy-model"


@pytest.mark.parametrize("status", [400, 404, 422])
def test_client_errors_not_retried(status: int) -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(status, text="bad")

    async def go() -> None:
        async with client_with(handler) as client:
            target = http_target(HttpTargetSpec(url="http://localhost/x"), client=client)
            await call_with_retries(target, {}, retries=3, timeout_s=5, sleep=no_sleep)

    with pytest.raises(CaseFailure, match=f"http {status}"):
        asyncio.run(go())
    assert calls["n"] == 1


@pytest.mark.parametrize("status", [408, 429, 500, 502])
def test_retriable_statuses(status: int) -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(status)

    async def go() -> None:
        async with client_with(handler) as client:
            target = http_target(HttpTargetSpec(url="http://localhost/x"), client=client)
            await call_with_retries(target, {}, retries=2, timeout_s=5, sleep=no_sleep)

    with pytest.raises(CaseFailure):
        asyncio.run(go())
    assert calls["n"] == 3


def test_connection_error_retried() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    async def go() -> None:
        async with client_with(handler) as client:
            target = http_target(HttpTargetSpec(url="http://localhost/x"), client=client)
            await call_with_retries(target, {}, retries=1, timeout_s=5, sleep=no_sleep)

    with pytest.raises(CaseFailure, match="connection error"):
        asyncio.run(go())


def test_allowlist_blocks_ssrf(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EVALGATE_HTTP_ALLOWED_HOSTS", "localhost,toy-targets")
    check_allowed("http://toy-targets:8110/classify")
    with pytest.raises(InvalidInputError, match=r"169\.254\.169\.254"):
        check_allowed("http://169.254.169.254/latest/meta-data")
    with pytest.raises(InvalidInputError, match="scheme"):
        check_allowed("file:///etc/passwd")
    monkeypatch.setenv("EVALGATE_HTTP_ALLOWED_HOSTS", "*")
    check_allowed("https://example.org/x")


def test_get_and_text_bodies() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.params["q"] == "x"
        return httpx.Response(200, text="plain answer")

    async def go() -> Any:
        async with client_with(handler) as client:
            target = http_target(HttpTargetSpec(url="http://localhost/x", method="GET"), client=client)
            return await target({"q": "x"})

    assert asyncio.run(go()).output == "plain answer"


def test_coerce_steps_is_lenient() -> None:
    steps = coerce_steps([{"name": "search", "kind": "weird", "input_tokens": -1}, "junk", {"node": "n"}])
    assert [s.node for s in steps] == ["search", "n"]
    assert steps[0].kind == "other"
