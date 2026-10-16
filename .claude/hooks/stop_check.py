#!/usr/bin/env python3
"""Stop hook: runs `make check-fast`; on failure blocks the stop once with a summary."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        payload = {}
    if payload.get("stop_hook_active"):
        return 0
    root = Path(__file__).resolve().parents[2]
    command = os.environ.get("EVALGATE_STOP_CHECK_CMD", "make check-fast")
    result = subprocess.run(  # noqa: S602 - fixed command or test override
        command, shell=True, cwd=root, capture_output=True, text=True, timeout=600, check=False
    )
    if result.returncode == 0:
        return 0
    tail = "\n".join((result.stdout + result.stderr).strip().splitlines()[-15:])
    print(json.dumps({"decision": "block", "reason": f"`{command}` failed:\n{tail}"}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
