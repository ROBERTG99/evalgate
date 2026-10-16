"""Custom metric registry: ``@evalgate.metric("name")``."""

from __future__ import annotations

import importlib
import inspect
from collections.abc import Callable
from typing import Any

from evalgate.contracts import Case, MetricScore, MetricSpec, TargetResult
from evalgate.metrics.base import BaseMetric, clamp

CustomFn = Callable[..., Any]
_REGISTRY: dict[str, CustomFn | type[Any]] = {}


def metric(name: str) -> Callable[[CustomFn], CustomFn]:
    """Register a custom metric.

    The decorated function is called as ``fn(case, result, params)`` (``params`` optional) and returns
    a float in [0, 1], a bool, or a :class:`MetricScore`. A decorated class is instantiated with the
    params dict and must provide ``score(case, result)``.
    """

    def decorator(fn: CustomFn) -> CustomFn:
        if name in _REGISTRY and _REGISTRY[name] is not fn:
            raise ValueError(f"metric {name!r} is already registered")
        _REGISTRY[name] = fn
        return fn

    return decorator


def registered() -> list[str]:
    return sorted(_REGISTRY)


def unregister(name: str) -> None:
    _REGISTRY.pop(name, None)


def resolve_custom(name: str) -> CustomFn | type[Any]:
    if name in _REGISTRY:
        return _REGISTRY[name]
    prefix, _, sub = name.partition(":")
    if sub and prefix in ("ragas", "deepeval"):
        module = importlib.import_module(f"evalgate.adapters.{prefix}")
        factory: CustomFn = module.make_metric(sub)
        return factory
    raise KeyError(f"unknown custom metric {name!r}; registered: {', '.join(registered()) or 'none'}")


class CustomMetric(BaseMetric):
    default_pass_at = 0.5

    def __init__(self, spec: MetricSpec) -> None:
        super().__init__(spec)
        target_name = str(self.params.get("metric", spec.name))
        impl = resolve_custom(target_name)
        options = {k: v for k, v in self.params.items() if k not in ("metric", "pass_at")}
        self._options = options
        if inspect.isclass(impl):
            factory: Any = impl
            self._obj: Any = factory(options)
            self._fn: CustomFn | None = None
        else:
            self._obj = None
            self._fn = impl
            self._arity = len(inspect.signature(impl).parameters)

    def score(self, case: Case, result: TargetResult) -> MetricScore:
        if self._obj is not None:
            raw = self._obj.score(case, result)
        else:
            assert self._fn is not None
            raw = self._fn(case, result, self._options) if self._arity >= 3 else self._fn(case, result)
        if isinstance(raw, MetricScore):
            return raw.model_copy(update={"name": self.name, "value": clamp(raw.value)})
        if isinstance(raw, tuple):
            value, details = raw
            return self.make(float(value), **dict(details))
        return self.make(float(raw))


def build_metric(spec: MetricSpec, **judge_kwargs: Any) -> Any:
    """Build a metric object from its spec."""
    from evalgate.metrics.builtin import BUILTIN

    if spec.kind in BUILTIN:
        return BUILTIN[spec.kind](spec)
    if spec.kind == "custom":
        return CustomMetric(spec)
    if spec.kind == "judge":
        from evalgate.judge.metric import JudgeMetric

        return JudgeMetric(spec, **judge_kwargs)
    raise KeyError(spec.kind)
