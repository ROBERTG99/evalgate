"""Python targets used by test suites."""

from __future__ import annotations

import asyncio
from typing import Any


def echo(case_input: dict[str, Any]) -> dict[str, Any]:
    return {"text": case_input.get("text", ""), "label": case_input.get("label", "")}


async def slow(case_input: dict[str, Any]) -> dict[str, Any]:
    await asyncio.sleep(float(case_input.get("sleep_s", 0.2)))
    return {"text": case_input.get("text", "")}


def boom(case_input: dict[str, Any]) -> dict[str, Any]:
    raise RuntimeError("target exploded")
