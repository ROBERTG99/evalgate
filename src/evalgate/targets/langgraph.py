"""``langgraph: "module:graph"`` targets: one StepRecord per executed node (extra ``[langgraph]``)."""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any

from evalgate.contracts import StepRecord, TargetResult
from evalgate.errors import InvalidInputError
from evalgate.targets.base import Target
from evalgate.targets.python import import_object


def _usage(update: Any) -> tuple[str | None, int, int]:
    """Read optional token usage a node reports under ``_usage`` ({model, input_tokens, output_tokens})."""
    if isinstance(update, dict) and isinstance(update.get("_usage"), dict):
        u = update["_usage"]
        return u.get("model"), int(u.get("input_tokens", 0)), int(u.get("output_tokens", 0))
    return None, 0, 0


def langgraph_target(ref: str) -> Target:
    graph = import_object(ref)
    if not hasattr(graph, "astream"):
        raise InvalidInputError(ref, "$.target.langgraph", "object has no astream(); pass a compiled graph")

    async def call(case_input: dict[str, Any]) -> TargetResult:
        steps: list[StepRecord] = []
        final: Any = None
        last = time.perf_counter()
        async for mode, chunk in graph.astream(case_input, stream_mode=["updates", "values"]):
            if mode == "values":
                final = chunk
                continue
            now = time.perf_counter()
            for node, update in (chunk or {}).items():
                model, tin, tout = _usage(update)
                steps.append(
                    StepRecord(
                        step=len(steps),
                        node=str(node),
                        kind="llm" if model else "other",
                        model=model,
                        input_tokens=tin,
                        output_tokens=tout,
                        latency_ms=(now - last) * 1000,
                        started_at=datetime.now(UTC),
                    )
                )
            last = now
        output = dict(final) if isinstance(final, dict) else {"value": final}
        output.pop("_usage", None)
        return TargetResult(output=output, steps=steps)

    return call
