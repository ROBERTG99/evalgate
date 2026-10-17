"""Cassettes: recorded provider responses keyed by route, model, prompt version and request."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from evalgate.contracts import Cassette
from evalgate.errors import CassetteMismatchError
from evalgate.ids import canonical_json, sha256_text
from evalgate.llm.types import LLMRequest


def cassette_key(route: str, model: str, prompt_version: str, messages: list[dict[str, str]], schema_name: str) -> str:
    """``sha256(route | model | prompt_version | canonical_json(messages, schema_name))``."""
    payload = canonical_json([messages, schema_name])
    return sha256_text(f"{route}|{model}|{prompt_version}|{payload}")


def request_key(req: LLMRequest) -> str:
    return cassette_key(req.route, req.model, req.prompt_version, req.messages, req.schema_name)


def request_digest(req: LLMRequest) -> str:
    """Digest of everything that shapes the response: system prompt, schema, effort and limits too."""
    return sha256_text(
        canonical_json(
            {
                "route": req.route,
                "model": req.model,
                "prompt_version": req.prompt_version,
                "system": req.system,
                "messages": req.messages,
                "schema_name": req.schema_name,
                "schema": req.schema,
                "effort": req.effort,
                "max_tokens": req.max_tokens,
            }
        )
    )


def default_dir() -> Path:
    return Path(os.environ.get("EVALGATE_CASSETTE_DIR", "tests/fixtures/llm"))


def cassette_path(root: Path, route: str, key: str) -> Path:
    return root / route / f"{key}.json"


def load(root: Path, req: LLMRequest) -> Cassette | None:
    """Return the cassette for ``req`` or None. A cassette whose digest differs raises CassetteMismatch."""
    key = request_key(req)
    path = cassette_path(root, req.route, key)
    if not path.is_file():
        return None
    cassette = Cassette.model_validate(json.loads(path.read_text(encoding="utf-8")))
    digest = request_digest(req)
    if cassette.request_digest != digest:
        raise CassetteMismatchError(
            f"cassette {path} has request_digest {cassette.request_digest[:12]}…, request has {digest[:12]}…; "
            "re-record it with `make record-fixtures`"
        )
    return cassette


def save(root: Path, req: LLMRequest, response: dict[str, Any], input_tokens: int, output_tokens: int) -> Path:
    key = request_key(req)
    cassette = Cassette(
        key=key,
        route=req.route,
        model=req.model,
        prompt_version=req.prompt_version,
        request_digest=request_digest(req),
        response=response,
        usage={"input_tokens": input_tokens, "output_tokens": output_tokens},
        recorded_at=datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
    )
    path = cassette_path(root, req.route, key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cassette.model_dump(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path
