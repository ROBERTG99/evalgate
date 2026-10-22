#!/usr/bin/env python3
"""PreToolUse hook (Bash|Write|Edit|MultiEdit|NotebookEdit): blocks actions the project forbids (see CLAUDE.md, "Never do").

Exit code 2 blocks the tool call and shows stderr to Claude. Malformed input fails closed for Bash.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

ROOT = Path(os.environ.get("EVALGATE_GUARD_ROOT") or Path(__file__).resolve().parents[2])
PROTECTED_DIRS = ("evals/datasets/", "evals/baselines/")
TRAILER = re.compile(
    r"^\s*(Co-Authored-By|Claude-Session)\s*:|Generated with \[?Claude Code",
    re.IGNORECASE | re.MULTILINE,
)
ENV_ASSIGN = re.compile(r"^(?:export\s+)?GIT_(AUTHOR|COMMITTER)_(NAME|EMAIL|DATE)=")
GIT_GLOBAL_WITH_ARG = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path"}
CONFIG_READ = {"--get", "--get-all", "--get-regexp", "--list", "-l", "--show-origin", "--name-only"}
GH_REPO_FORBIDDEN = {"create", "edit", "delete", "fork", "rename", "archive", "unarchive", "transfer"}


def segments(command: str) -> list[list[str]]:
    """Quote-aware split into simple commands; ``;``, ``&``, ``|`` and redirections become own tokens."""
    lexer = shlex.shlex(command.replace("\\\n", " "), posix=True, punctuation_chars=";&|<>")
    lexer.whitespace_split = True
    lexer.commenters = ""
    try:
        toks = list(lexer)
    except ValueError:
        toks = command.split()
    out: list[list[str]] = [[]]
    for tok in toks:
        if tok and set(tok) <= set(";&|"):
            out.append([])
        else:
            out[-1].append(tok)
    return [seg for seg in out if seg]


def protected(path_text: str, cwd: Path) -> str | None:
    path = Path(os.path.expanduser(path_text))
    if not path.is_absolute():
        path = cwd / path
    try:
        rel = path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return None
    if rel.endswith("MANIFEST.json"):  # regenerated whenever a new dataset version is added
        return None
    if (rel.startswith(PROTECTED_DIRS) or rel + "/" in PROTECTED_DIRS or rel == "evals") and committed(rel, path):
        return rel
    return None


def committed(rel: str, path: Path) -> bool:
    """Committed (tracked) files are append-only; outside a git checkout, any existing file is."""
    if not (ROOT / ".git").exists():
        return path.exists()
    try:
        out = subprocess.run(
            ["git", "-C", str(ROOT), "ls-files", "--", rel], capture_output=True, text=True, timeout=10, check=False
        )
    except (OSError, subprocess.SubprocessError):
        return path.exists()
    return bool(out.stdout.strip())


def message_blocked(values: list[str], cwd: Path) -> bool:
    return any(TRAILER.search(v) for v in values)


def read_file(path_text: str, cwd: Path) -> str:
    path = Path(os.path.expanduser(path_text))
    path = path if path.is_absolute() else cwd / path
    try:
        return path.read_text(encoding="utf-8", errors="replace")[:200_000]
    except OSError:
        return ""


def option_values(args: list[str], names: set[str], cwd: Path, file_names: set[str]) -> list[str]:
    """Values of options such as -m/--message (inline or separate) and contents of -F/--file."""
    out: list[str] = []
    i = 0
    while i < len(args):
        arg = args[i]
        for name in names | file_names:
            value: str | None = None
            if arg == name and i + 1 < len(args):
                value = args[i + 1]
            elif name.startswith("--") and arg.startswith(name + "="):
                value = arg[len(name) + 1 :]
            elif not name.startswith("--") and arg.startswith(name) and len(arg) > len(name):
                value = arg[len(name) :]
            if value is not None:
                out.append(read_file(value, cwd) if name in file_names and value != "-" else value)
        i += 1
    return out


def check_git(args: list[str], cwd: Path) -> str | None:
    i = 0
    while i < len(args) and args[i].startswith("-"):
        opt = args[i]
        if opt == "-c" and i + 1 < len(args) and args[i + 1].lower().startswith("user."):
            return "changing git identity is forbidden"
        if opt.startswith("-c") and opt[2:].lower().startswith("user."):
            return "changing git identity is forbidden"
        if opt == "-C" and i + 1 < len(args):
            cwd = cwd / args[i + 1]
        i += 2 if opt in GIT_GLOBAL_WITH_ARG else 1
    if i >= len(args):
        return None
    sub, rest = args[i], args[i + 1 :]
    if sub == "push":
        for arg in rest:
            if arg.startswith("--force") or arg in ("--mirror", "--tags", "--follow-tags"):
                return "force pushes and tag pushes are forbidden"
            if re.fullmatch(r"-[A-Za-z]*f[A-Za-z]*", arg):
                return "force pushes are forbidden"
            if arg.startswith("+") or re.search(r"(^|:)refs/tags/|^v\d+\.\d+\.\d+$", arg):
                return "force pushes and tag pushes are forbidden"
    if sub == "config" and any(a.lower().startswith("user.") for a in rest) and not any(a in CONFIG_READ for a in rest):
        return "changing git identity is forbidden"
    if sub in ("commit", "tag", "notes", "merge"):
        values = option_values(rest, {"-m", "--message", "--trailer"}, cwd, {"-F", "--file"})
        if message_blocked(values, cwd):
            return "commit attribution trailers are forbidden"
    return None


def check_gh(args: list[str], cwd: Path) -> str | None:
    if len(args) >= 2 and args[0] == "repo" and args[1] in GH_REPO_FORBIDDEN:
        return "creating or changing repositories is forbidden"
    if len(args) >= 2 and args[0] == "release" and args[1] in ("create", "edit", "upload", "delete"):
        return "publishing releases is maintainer only"
    if args and args[0] == "api" and any("visibility" in a or a.startswith("user/repos") for a in args):
        return "changing repository visibility is forbidden"
    if len(args) >= 2 and args[0] == "pr" and args[1] in ("create", "edit", "comment", "review"):
        values = option_values(args[2:], {"-b", "--body", "-t", "--title"}, cwd, {"-F", "--body-file"})
        if message_blocked(values, cwd):
            return "pull request attribution is forbidden"
    return None


def check_rm(args: list[str]) -> str | None:
    flags = "".join(a.lstrip("-") for a in args if a.startswith("-") and not a.startswith("--"))
    long_flags = {a for a in args if a.startswith("--")}
    recursive = "r" in flags or "R" in flags or "--recursive" in long_flags
    targets = [a for a in args if not a.startswith("-")]
    if recursive and any(t in ("/", "/*", "~", "~/", "~/*", "$HOME", "$HOME/") for t in targets):
        return "recursive delete of / or ~ is forbidden"
    return None


def check_segment(toks: list[str], cwd: Path) -> str | None:
    for i, tok in enumerate(toks):
        if ENV_ASSIGN.match(tok):
            return "setting GIT_AUTHOR_*/GIT_COMMITTER_* is forbidden"
        if tok in (">", ">>", ">|") and i + 1 < len(toks):
            rel = protected(toks[i + 1], cwd)
            if rel:
                return f"{rel} is append-only: add a new versioned file instead of editing it"
    toks = [
        t
        for i, t in enumerate(toks)
        if t not in (">", ">>", ">|", "<") and (i == 0 or toks[i - 1] not in (">", ">>", ">|", "<"))
    ]
    while toks and (re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", toks[0]) or toks[0] == "export"):
        toks = toks[1:]
    while toks and toks[0] in ("sudo", "env", "command", "exec", "time", "nohup"):
        toks = toks[1:]
    if not toks:
        return None
    cmd, args = os.path.basename(toks[0]), toks[1:]
    if cmd == "terraform" and args and args[0] in ("apply", "destroy"):
        return "terraform apply/destroy is forbidden"
    if cmd == "git":
        return check_git(args, cwd)
    if cmd == "gh":
        return check_gh(args, cwd)
    if cmd == "rm":
        reason = check_rm(args)
        if reason:
            return reason
    editors = {
        "sed": lambda a: "-i" in a or any(x.startswith("-i") or x == "--in-place" for x in a),
        "tee": lambda a: True,
        "truncate": lambda a: True,
        "rm": lambda a: True,
        "perl": lambda a: "-i" in a,
    }
    if cmd in editors and editors[cmd](args):
        for arg in args:
            if not arg.startswith("-") and protected(arg, cwd):
                return f"{protected(arg, cwd)} is append-only: add a new versioned file instead of editing it"
    if cmd in ("mv", "cp", "install", "ln") and args:
        dest = [a for a in args if not a.startswith("-")]
        if dest and protected(dest[-1], cwd):
            return f"{protected(dest[-1], cwd)} is append-only: add a new versioned file instead of editing it"
        if cmd == "mv" and any(protected(a, cwd) for a in dest[:-1]):
            return "moving committed datasets or baselines is forbidden"
    return None


COMMIT_LIKE = re.compile(r"\bgit\s+(?:-\S+\s+)*(commit|tag|notes)\b|\bgh\s+pr\s+(create|edit|comment)\b")
HEREDOC = re.compile(r"<<-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1[^\n]*\n(.*?)\n\s*\2\s*(?:\n|$)", re.S)


def split_heredocs(command: str) -> tuple[str, list[str]]:
    """Remove heredoc bodies (data, not commands) and return them separately."""
    bodies: list[str] = []

    def keep_head(match: re.Match[str]) -> str:
        bodies.append(match.group(3))
        head = match.group(0).split("\n", 1)[0]
        return head + "\n"

    return HEREDOC.sub(keep_head, command), bodies


def check_bash(command: str, cwd: Path) -> str | None:
    command, bodies = split_heredocs(command)
    if COMMIT_LIKE.search(command) and any(TRAILER.search(b) for b in bodies):
        return "commit attribution trailers are forbidden"
    for segment in segments(command):
        # Unquoted newlines are not separators for shlex, so also check from every command-like token.
        starts = [0] + [i for i, t in enumerate(segment) if i and t in ("git", "gh", "terraform", "rm", "sed", "tee")]
        for start in starts:
            reason = check_segment(segment[start:], cwd)
            if reason:
                return reason
    return None


def check_write(tool_input: dict[str, object], cwd: Path) -> str | None:
    file_path = str(tool_input.get("file_path") or tool_input.get("notebook_path") or "")
    rel = protected(file_path, cwd)
    if rel:
        return f"{rel} is append-only: add a new versioned file instead of editing it"
    if re.search(r"(^|/)\.env(\.(?!example$)[^/]+)?$", file_path):
        return "writing .env files is forbidden"
    if file_path.endswith("COMMIT_EDITMSG"):
        texts = [str(tool_input.get("content", "")), str(tool_input.get("new_string", ""))]
        edits = tool_input.get("edits")
        if isinstance(edits, list):
            texts += [str(e.get("new_string", "")) for e in edits if isinstance(e, dict)]
        if message_blocked(texts, cwd):
            return "commit attribution trailers are forbidden"
    return None


def main() -> int:
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise TypeError("payload is not an object")
    except (json.JSONDecodeError, ValueError, TypeError):
        print("Blocked by .claude/hooks/pre_tool_guard.py: unreadable hook input", file=sys.stderr)
        return 2
    tool = payload.get("tool_name", "")
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        tool_input = {}
    cwd = Path(str(payload.get("cwd") or os.getcwd()))
    reason: str | None = None
    if tool == "Bash":
        reason = check_bash(str(tool_input.get("command", "")), cwd)
    elif tool in {"Write", "Edit", "MultiEdit", "NotebookEdit"}:
        reason = check_write(tool_input, cwd)
    if reason:
        print(f"Blocked by .claude/hooks/pre_tool_guard.py: {reason}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
