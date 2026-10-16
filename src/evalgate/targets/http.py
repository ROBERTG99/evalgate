"""``http`` targets: JSON over HTTP with a host allowlist (SSRF guard)."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

import httpx

from evalgate import config
from evalgate.contracts import HttpTargetSpec, TargetResult
from evalgate.errors import InvalidInputError
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


def http_target(spec: HttpTargetSpec, client: httpx.AsyncClient | None = None) -> Target:
    check_allowed(spec.url)
    shared = client

    async def call(case_input: dict[str, Any]) -> TargetResult:
        own = shared is None
        http = shared or httpx.AsyncClient(timeout=spec.timeout_s)
        try:
            if spec.method == "GET":
                resp = await http.get(spec.url, params=case_input, headers=spec.headers, timeout=spec.timeout_s)
            else:
                resp = await http.request(
                    spec.method, spec.url, json=case_input, headers=spec.headers, timeout=spec.timeout_s
                )
        except httpx.TimeoutException as exc:
            raise RetriableTargetError(f"http timeout: {exc.__class__.__name__}") from exc
        except httpx.TransportError as exc:
            raise RetriableTargetError(f"connection error: {exc.__class__.__name__}") from exc
        finally:
            if own:
                await http.aclose()
        if resp.status_code in RETRIABLE_STATUS or resp.status_code >= 500:
            raise RetriableTargetError(f"http {resp.status_code}")
        if resp.status_code >= 400:
            raise TargetError(f"http {resp.status_code}: {resp.text[:200]}")
        try:
            body = resp.json()
        except ValueError:
            body = resp.text
        result = coerce_result(body)
        return result

    return call
