"""Broken custom metrics for runner tests (loaded through a suite's ``plugins``)."""

from __future__ import annotations

from typing import Any

import evalgate


@evalgate.metric("nan_metric")
def nan_metric(case: Any, result: Any) -> float:
    return float("nan")


@evalgate.metric("raising_metric")
def raising_metric(case: Any, result: Any) -> float:
    raise RuntimeError("metric exploded")
