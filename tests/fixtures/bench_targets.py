"""Targets used by scripts/bench.py."""

from __future__ import annotations

import asyncio
from typing import Any


async def sleepy(case_input: dict[str, Any]) -> dict[str, Any]:
    await asyncio.sleep(0.2)
    return {"label": "a", "answer": case_input.get("answer", "")}


async def noop(case_input: dict[str, Any]) -> dict[str, Any]:
    return {"label": "a", "answer": case_input.get("answer", "")}
