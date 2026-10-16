"""Fail when the wheel is over 1 MB or ships files outside src/evalgate (NFR-7)."""

from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path

LIMIT = 1_000_000


def main() -> int:
    dist = Path(sys.argv[1] if len(sys.argv) > 1 else "dist")
    wheels = sorted(dist.glob("evalgate-*.whl"))
    if not wheels:
        print("no evalgate wheel in dist/", file=sys.stderr)
        return 1
    wheel = wheels[-1]
    size = wheel.stat().st_size
    names = zipfile.ZipFile(wheel).namelist()
    foreign = [n for n in names if not n.startswith(("evalgate/", "evalgate-"))]
    required = {
        "evalgate/pricing.yaml",
        "evalgate/prompts/judge_answer_correctness.v1.md",
        "evalgate/viewer/static/tokens.css",
        "evalgate/store/migrations/001_init.sql",
    }
    missing = sorted(required - set(names))
    result = {
        "wheel": wheel.name,
        "bytes": size,
        "limit": LIMIT,
        "files": len(names),
        "foreign": foreign,
        "missing": missing,
        "passed": size < LIMIT and not foreign and not missing,
    }
    (dist / "wheel-check.json").write_text(json.dumps(result, indent=2) + "\n")
    print(
        f"wheel: {wheel.name} {size:,} bytes (limit {LIMIT:,}), {len(names)} files"
        + (f"; foreign files: {foreign}" if foreign else "")
        + (f"; missing: {missing}" if missing else "")
    )
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
