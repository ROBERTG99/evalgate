"""``http`` targets: JSON over HTTP with a host allowlist (SSRF guard)."""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlsplit

import httpx

from evalgate import config
from evalgate.contracts import HttpTargetSpec, TargetResult
from evalgate.errors import InvalidInputError
from evalgate.suite.limits import MAX_TARGET_OUTPUT_BYTES
from evalgate.targets.base import RetriableTargetError, Target, TargetError, coerce_result

RETRIABLE_STATUS = {408, 429}


def check_allowed(url: str, allowed: set[str] | None = None) -> None:
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https"):
        raise InvalidInputError(url, "$.target.http.url", f"scheme {parts.scheme!r} is not http or https")
    host = (parts.hostname or "").lower()
    allowed = config.http_allowed_hosts() if allowed is None else allowed
    if "*" not in allowed and host not in allowed:
        raise InvalidInputError(
            url,
            "$.target.http.url",
            f"host {host!r} is not in EVALGATE_HTTP_ALLOWED_HOSTS ({', '.join(sorted(allowed))})",
        )


async def _read_capped(resp: httpx.Response) -> bytes:
    """Read the body but stop at ``MAX_TARGET_OUTPUT_BYTES``: target output is untrusted (memory DoS)."""
    chunks: list[bytes] = []
    size = 0
    async for chunk in resp.aiter_bytes():
        size += len(chunk)
        if size > MAX_TARGET_OUTPUT_BYTES:
            raise TargetError(f"response body is over the {MAX_TARGET_OUTPUT_BYTES}-byte limit")
        chunks.append(chunk)
    return b"".join(chunks)


def http_target(spec: HttpTargetSpec, client: httpx.AsyncClient | None = None) -> Target:
    check_allowed(spec.url)
    shared = client

    async def call(case_input: dict[str, Any]) -> TargetResult:
        own = shared is None
        http = shared or httpx.AsyncClient(timeout=spec.timeout_s)
        kwargs: dict[str, Any] = {"params": case_input} if spec.method == "GET" else {"json": case_input}
        try:
            async with http.stream(
                spec.method, spec.url, headers=spec.headers, timeout=spec.timeout_s, **kwargs
            ) as resp:
                status = resp.status_code
                content = await _read_capped(resp)
        except httpx.TimeoutException as exc:
            raise RetriableTargetError(f"http timeout: {exc.__class__.__name__}") from exc
        except httpx.TransportError as exc:
            raise RetriableTargetError(f"connection error: {exc.__class__.__name__}") from exc
        finally:
            if own:
                await http.aclose()
        if status in RETRIABLE_STATUS or status >= 500:
            raise RetriableTargetError(f"http {status}")
        text = content.decode("utf-8", errors="replace")
        if status >= 400:
            raise TargetError(f"http {status}: {text[:200]}")
        try:
            body = json.loads(text)
        except ValueError:
            body = text
        return coerce_result(body)

    return call
