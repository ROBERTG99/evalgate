"""YAML suite and JSONL dataset loader (FR-1)."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ValidationError

from evalgate.contracts import Case, Suite
from evalgate.errors import InvalidInputError
from evalgate.suite.limits import (
    MAX_SUITE_BYTES,
    check_case_count,
    check_file_size,
    check_row_size,
)
from evalgate.suite.selectors import SelectorError, validate_selector

_VAR = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-([^}]*))?\}")


@dataclass
class LoadedSuite:
    suite: Suite
    path: Path
    dataset_path: Path
    cases: list[Case] = field(default_factory=list)


def json_path(loc: tuple[int | str, ...]) -> str:
    out = "$"
    for part in loc:
        out += f"[{part}]" if isinstance(part, int) else f".{part}"
    return out


def _describe(err: Any) -> tuple[str, str]:
    loc = tuple(p for p in err["loc"] if not (isinstance(p, str) and p.startswith("function-")))
    if err["type"] == "extra_forbidden":
        return json_path(loc), f"unknown key {loc[-1]!r}"
    if err["type"] == "missing":
        return json_path(loc), f"missing required key {loc[-1]!r}"
    return json_path(loc), str(err["msg"])


def validation_error(path: Path | str, exc: ValidationError, prefix: str = "") -> InvalidInputError:
    # Unknown keys first: a typo such as `metircs` also causes a "missing key" error for `metrics`.
    errors = sorted(exc.errors(), key=lambda e: e["type"] != "extra_forbidden")
    location, problem = _describe(errors[0])
    extra = len(exc.errors()) - 1
    if extra:
        problem += f" (and {extra} more problem{'s' if extra > 1 else ''})"
    return InvalidInputError(str(path), f"{prefix}{location}", problem)


def interpolate(value: Any) -> Any:
    """Expand ``${VAR}`` and ``${VAR:-default}`` in strings (used for ``target`` only)."""
    if isinstance(value, str):
        return _VAR.sub(lambda m: os.environ.get(m.group(1)) or (m.group(2) or ""), value)
    if isinstance(value, dict):
        return {k: interpolate(v) for k, v in value.items()}
    if isinstance(value, list):
        return [interpolate(v) for v in value]
    return value


def read_yaml(path: Path, limit: int = MAX_SUITE_BYTES) -> dict[str, Any]:
    if not path.is_file():
        raise InvalidInputError(str(path), "", "file not found")
    check_file_size(path, limit, "file")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        where = f"line {mark.line + 1}" if mark is not None else ""
        raise InvalidInputError(str(path), where, f"invalid YAML: {getattr(exc, 'problem', exc)}") from exc
    if not isinstance(data, dict):
        raise InvalidInputError(str(path), "$", "expected a mapping at the top level")
    return data


def parse_model[M: BaseModel](model: type[M], data: dict[str, Any], path: Path) -> M:
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        raise validation_error(path, exc) from exc


def resolve_relative(ref: str, base_file: Path) -> Path:
    """Paths in suites resolve against the working directory, then the suite's folder."""
    candidate = Path(ref)
    if candidate.is_absolute() or candidate.exists():
        return candidate
    beside = base_file.parent / ref
    return beside if beside.exists() else candidate


def load_suite_file(path: Path) -> Suite:
    data = read_yaml(path)
    if "target" in data:
        data["target"] = interpolate(data["target"])
    suite = parse_model(Suite, data, path)
    for i, metric in enumerate(suite.metrics):
        for key in ("actual", "candidate"):
            value = metric.params.get(key)
            if value is None:
                continue
            try:
                validate_selector(str(value))
            except SelectorError as exc:
                raise InvalidInputError(str(path), f"$.metrics[{i}].params.{key}", str(exc)) from exc
    return suite


def load_dataset(path: Path, splits: list[str] | None = None) -> list[Case]:
    if not path.is_file():
        raise InvalidInputError(str(path), "", "dataset file not found")
    cases: list[Case] = []
    seen: dict[str, int] = {}
    with path.open("rb") as fh:
        for line_no, raw in enumerate(fh, start=1):
            check_row_size(path, line_no, raw)
            if not raw.strip():
                continue
            try:
                data = json.loads(raw)
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                raise InvalidInputError(str(path), f"line {line_no}", f"invalid JSON: {exc}") from exc
            if not isinstance(data, dict):
                raise InvalidInputError(str(path), f"line {line_no}", "expected a JSON object")
            try:
                case = Case.model_validate(data)
            except ValidationError as exc:
                raise validation_error(path, exc, prefix=f"line {line_no} ") from exc
            if case.id in seen:
                raise InvalidInputError(
                    str(path),
                    f"line {line_no}",
                    f"duplicate id {case.id!r} (first seen on line {seen[case.id]})",
                )
            seen[case.id] = line_no
            cases.append(case)
            check_case_count(path, len(cases))
    if splits is not None:
        cases = [c for c in cases if c.split in splits]
    return cases


def load_suite(path: str | Path, split: str | None = None) -> LoadedSuite:
    suite_path = Path(path)
    suite = load_suite_file(suite_path)
    dataset_path = resolve_relative(suite.dataset, suite_path)
    if split is not None and split not in suite.splits:
        raise InvalidInputError(str(suite_path), "$.splits", f"split {split!r} is not declared by the suite")
    cases = load_dataset(dataset_path, [split] if split else list(suite.splits))
    return LoadedSuite(suite=suite, path=suite_path, dataset_path=dataset_path, cases=cases)
