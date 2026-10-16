"""Export the Pydantic contracts to schemas/*.json. ``--check`` fails (exit 1) on drift."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from evalgate.contracts import SCHEMA_MODELS, json_schema

ROOT = Path(__file__).resolve().parents[1]


def render(name: str) -> str:
    return json.dumps(json_schema(name), indent=2, sort_keys=False) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail when schemas/ differs from the models")
    parser.add_argument("--out", type=Path, default=ROOT / "schemas")
    args = parser.parse_args()
    drift = []
    args.out.mkdir(parents=True, exist_ok=True)
    for name in SCHEMA_MODELS:
        path = args.out / f"{name}.json"
        text = render(name)
        if path.exists() and path.read_text(encoding="utf-8") == text:
            continue
        drift.append(path.name)
        if not args.check:
            path.write_text(text, encoding="utf-8")
    if args.check and drift:
        print(f"schema drift: {', '.join(drift)}; run `make schemas` without --check", file=sys.stderr)
        return 1
    print(
        f"schemas: {len(SCHEMA_MODELS)} files {'checked' if args.check else 'written'}"
        + (f", updated {', '.join(drift)}" if drift and not args.check else "")
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
