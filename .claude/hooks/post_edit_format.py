#!/usr/bin/env python3
"""PostToolUse hook (Write|Edit): ruff format and fix on edited Python files; no-op without ruff."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path


def ruff_command() -> list[str] | None:
    root = Path(__file__).resolve().parents[2]
    venv_ruff = root / ".venv" / "bin" / "ruff"
    if venv_ruff.exists():
        return [str(venv_ruff)]
    found = shutil.which("ruff")
    return [found] if found else None


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0
    path = (payload.get("tool_input") or {}).get("file_path", "")
    if not path.endswith(".py") or not Path(path).exists():
        return 0
    ruff = ruff_command()
    if ruff is None:
        return 0
    subprocess.run([*ruff, "format", "--quiet", path], check=False)
    subprocess.run([*ruff, "check", "--fix", "--quiet", path], check=False, capture_output=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
