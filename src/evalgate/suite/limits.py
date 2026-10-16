"""Size limits (NFR-11): suite and dataset row ≤ 1 MB, report ≤ 50 MB, ≤ 100,000 cases."""

from __future__ import annotations

from pathlib import Path

from evalgate.errors import InvalidInputError

MAX_SUITE_BYTES = 1_000_000
MAX_ROW_BYTES = 1_000_000
MAX_REPORT_BYTES = 50_000_000
MAX_CASES = 100_000


def check_file_size(path: Path, limit: int, what: str) -> None:
    size = path.stat().st_size
    if size > limit:
        raise InvalidInputError(str(path), "", f"{what} is {size} bytes, over the {limit}-byte limit")


def check_row_size(path: Path, line_no: int, raw: bytes) -> None:
    if len(raw) > MAX_ROW_BYTES:
        raise InvalidInputError(
            str(path), f"line {line_no}", f"row is {len(raw)} bytes, over the {MAX_ROW_BYTES}-byte limit"
        )


def check_case_count(path: Path, n: int) -> None:
    if n > MAX_CASES:
        raise InvalidInputError(str(path), "", f"{n} cases, over the {MAX_CASES}-case limit")
