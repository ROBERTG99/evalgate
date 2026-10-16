"""Target adapters."""

from __future__ import annotations

from typing import Any

from evalgate.contracts import TargetSpec
from evalgate.targets.base import RetriableTargetError, Target, TargetError, coerce_result


def build_target(spec: TargetSpec, **kwargs: Any) -> Target:
    if spec.python:
        from evalgate.targets.python import python_target

        return python_target(spec.python)
    if spec.http:
        from evalgate.targets.http import http_target

        return http_target(spec.http, client=kwargs.get("http_client"))
    assert spec.langgraph is not None
    from evalgate.targets.langgraph import langgraph_target

    return langgraph_target(spec.langgraph)


__all__ = ["RetriableTargetError", "Target", "TargetError", "build_target", "coerce_result"]
