"""Identifiers: UUIDv7 run ids (time-ordered) and canonical JSON digests."""

from __future__ import annotations

import hashlib
import json
import os
import time
import uuid
from typing import Any

RUN_ID_PATTERN = r"^[0-9a-f-]{36}$"


def uuid7() -> str:
    """RFC 9562 UUIDv7: 48-bit Unix milliseconds, version 7, variant 10, random tail."""
    ms = time.time_ns() // 1_000_000
    rand = int.from_bytes(os.urandom(10), "big")
    value = (ms & ((1 << 48) - 1)) << 80
    value |= 0x7 << 76
    value |= ((rand >> 62) & 0xFFF) << 64
    value |= 0b10 << 62
    value |= rand & ((1 << 62) - 1)
    return str(uuid.UUID(int=value))


def canonical_json(value: Any) -> str:
    """Sorted keys, no whitespace, UTF-8 (``ensure_ascii=False``)."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
