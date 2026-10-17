"""Coverage gates for ``make test``: >= 85% line coverage on the core packages, >= 70% overall.

Reads the JSON written by ``pytest --cov-report=json:<path>``; exit 1 on a miss.
Core packages (§10 of the build spec): suite, runner, targets, metrics, judge, stats, cache, store, report.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

CORE = ("suite", "runner", "targets", "metrics", "judge", "stats", "cache", "store", "report")
CORE_MIN = 85.0
OVERALL_MIN = 70.0


def package_of(path: str) -> str | None:
    parts = Path(path).parts
    if "evalgate" not in parts:
        return None
    rest = parts[parts.index("evalgate") + 1 :]
    return rest[0] if len(rest) > 1 else None


def gates(data: dict) -> list[tuple[str, float, float]]:
    covered: dict[str, int] = {}
    statements: dict[str, int] = {}
    for path, info in data["files"].items():
        package = package_of(path)
        if package in CORE:
            covered[package] = covered.get(package, 0) + info["summary"]["covered_lines"]
            statements[package] = statements.get(package, 0) + info["summary"]["num_statements"]
    rows = [("overall", float(data["totals"]["percent_covered"]), OVERALL_MIN)]
    for package in CORE:
        total = statements.get(package, 0)
        percent = 100.0 * covered.get(package, 0) / total if total else 0.0
        rows.append((package, percent, CORE_MIN))
    return rows


def main(argv: list[str]) -> int:
    path = Path(argv[1] if len(argv) > 1 else ".evalgate/coverage.json")
    rows = gates(json.loads(path.read_text(encoding="utf-8")))
    failed = False
    for name, percent, minimum in rows:
        ok = percent >= minimum
        failed |= not ok
        print(f"coverage {name:10} {percent:6.2f}% (min {minimum:.0f}%) {'ok' if ok else 'MISS'}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
