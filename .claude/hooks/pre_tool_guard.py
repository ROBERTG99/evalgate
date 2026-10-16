#!/usr/bin/env python3
"""PreToolUse hook (Bash|Write|Edit): blocks the forbidden actions of the build spec.

Exit code 2 blocks the tool call and shows stderr to Claude.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

BASH_RULES: list[tuple[str, str]] = [
    (r"\bterraform\s+(apply|destroy)\b", "terraform apply/destroy is forbidden"),
    (
        r"\bgit\s+push\b[^\n;&|]*(\s--force\b|\s--force-with-lease\b|\s-f\b|\s\+\S)",
        "force pushes are forbidden",
    ),
    (r"\bgit\s+push\b[^\n;&|]*\s--tags\b", "pushing tags is maintainer only"),
    (r"(^|[;&|(]|\n)\s*git\s+(-\S+\s+)*config\b[^\n;&|]*\buser\.", "changing git identity is forbidden"),
    (
        r"(^|[\s;&|(])(export\s+)?GIT_(AUTHOR|COMMITTER)_(NAME|EMAIL|DATE)=",
        "setting GIT_AUTHOR_*/GIT_COMMITTER_* is forbidden",
    ),
    (r"\brm\s+-rf\s+(/|~)(\s|$|\*)", "recursive delete of / or ~ is forbidden"),
    (r"\bgh\s+repo\s+(create|edit|delete)\b", "creating or changing repositories is forbidden"),
    (r"\bgh\s+release\s+create\b", "publishing releases is maintainer only"),
]

TRAILERS = re.compile(r"Co-Authored-By|Claude-Session|Generated with Claude Code", re.IGNORECASE)
COMMIT_LIKE = re.compile(r"\bgit\s+(commit|tag|notes)\b|\bgh\s+pr\s+(create|edit|comment)\b")

PROTECTED_DIRS = ("evals/datasets/", "evals/baselines/")


def check_bash(command: str) -> str | None:
    for pattern, reason in BASH_RULES:
        if re.search(pattern, command):
            return reason
    if COMMIT_LIKE.search(command) and TRAILERS.search(command):
        return "commit attribution trailers are forbidden"
    return None


def check_write(file_path: str, cwd: str) -> str | None:
    path = Path(file_path)
    if not path.is_absolute():
        path = Path(cwd) / path
    root = Path(__file__).resolve().parents[2]
    try:
        rel = path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        rel = file_path
    if rel.startswith(PROTECTED_DIRS) and path.exists():
        return f"{rel} is append-only: add a new versioned file instead of editing it"
    if re.search(r"(^|/)\.env(\.(?!example$)[^/]+)?$", rel):
        return "writing .env files is forbidden"
    return None


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0
    tool = payload.get("tool_name", "")
    tool_input = payload.get("tool_input") or {}
    reason: str | None = None
    if tool == "Bash":
        reason = check_bash(str(tool_input.get("command", "")))
    elif tool in {"Write", "Edit", "MultiEdit", "NotebookEdit"}:
        reason = check_write(str(tool_input.get("file_path", "")), payload.get("cwd", "."))
        content = str(tool_input.get("content", "")) + str(tool_input.get("new_string", ""))
        if reason is None and str(tool_input.get("file_path", "")).endswith("COMMIT_EDITMSG"):
            reason = "commit attribution trailers are forbidden" if TRAILERS.search(content) else None
    if reason:
        print(f"Blocked by .claude/hooks/pre_tool_guard.py: {reason}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
