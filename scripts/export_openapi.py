"""Export the toy targets' OpenAPI document to docs/contracts/openapi/toy-targets.json. ``--check`` fails on drift.

The viewer has no OpenAPI document: it is a read-only stdlib server whose JSON routes are described in
``docs/architecture.md``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from toy_targets.app import create_app

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "contracts" / "openapi" / "toy-targets.json"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail when the committed document differs")
    args = parser.parse_args()
    text = json.dumps(create_app().openapi(), indent=2) + "\n"
    if OUT.exists() and OUT.read_text(encoding="utf-8") == text:
        print(f"openapi: {OUT.relative_to(ROOT)} up to date")
        return 0
    if args.check:
        print(f"openapi: {OUT.relative_to(ROOT)} drifted; run `make docs`", file=sys.stderr)
        return 1
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text, encoding="utf-8")
    print(f"openapi: wrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
