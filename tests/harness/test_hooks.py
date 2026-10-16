import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
HOOKS = ROOT / ".claude" / "hooks"


def run_hook(name: str, payload: dict, env: dict | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(HOOKS / name)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env={**os.environ, **(env or {})},
        check=False,
    )


def bash(command: str) -> subprocess.CompletedProcess[str]:
    return run_hook("pre_tool_guard.py", {"tool_name": "Bash", "tool_input": {"command": command}})


@pytest.mark.parametrize(
    "command",
    [
        "git push --force origin main",
        "git push -f origin feature",
        "git push origin +main",
        "git push --force-with-lease",
        "git -C . push --force origin main",
        "git push -uf origin main",
        "cd repo\ngit push --force origin main",
        "git -c user.name=X -c user.email=Y commit -m msg",
        "git -C /tmp config user.name X",
        "git commit -m 'feat: x' -m '🤖 Generated with [Claude Code](https://claude.com/claude-code)'",
        "git -C . commit -m 'feat: x\n\nCo-Authored-By: Claude <noreply@anthropic.com>'",
        "gh repo fork ROBERTG99/evalgate",
        "gh api -X PATCH repos/ROBERTG99/evalgate -f visibility=public",
        "git push origin v0.1.0",
        "git push --tags",
        "rm -fr /",
        "rm -r -f ~/",
        "git config user.name 'Someone'",
        "git config --global user.email a@b.c",
        "GIT_AUTHOR_NAME=x git commit -m msg",
        "export GIT_COMMITTER_EMAIL=x@y.z",
        "git commit -m 'feat: x\n\nCo-Authored-By: Claude <noreply@anthropic.com>'",
        "git commit -m 'feat: x' -m 'Claude-Session: https://claude.ai/code/x'",
        "gh pr create --body 'Generated with Claude Code'",
        "terraform apply -auto-approve",
        "terraform destroy",
        "rm -rf /",
        "rm -rf ~",
    ],
)
def test_forbidden_bash_blocked(command: str) -> None:
    result = bash(command)
    assert result.returncode == 2, command
    assert "Blocked" in result.stderr


@pytest.mark.parametrize(
    "command",
    [
        "git push -u origin claude/feature",
        "git commit -m 'feat: add metric'",
        "git log --format=%B | grep -E 'Co-Authored-By|Claude-Session' || true",
        "git config --get user.name",
        "git commit -m 'docs: explain why we never add a Co-Authored-By trailer'",
        "git push -u origin claude/fix-v1-baseline",
        "rm -rf build/",
        "make check-fast",
        "uv run pytest tests/unit",
    ],
)
def test_allowed_bash_passes(command: str) -> None:
    assert bash(command).returncode == 0, command


def test_commit_message_file_checked(tmp_path: Path) -> None:
    msg = tmp_path / "msg.txt"
    msg.write_text("feat: x\n\nCo-Authored-By: Claude <noreply@anthropic.com>\n")
    res = run_hook(
        "pre_tool_guard.py",
        {"tool_name": "Bash", "tool_input": {"command": f"git commit -F {msg}"}, "cwd": str(tmp_path)},
    )
    assert res.returncode == 2
    msg.write_text("feat: x\n")
    ok = run_hook(
        "pre_tool_guard.py",
        {"tool_name": "Bash", "tool_input": {"command": f"git commit -F {msg}"}, "cwd": str(tmp_path)},
    )
    assert ok.returncode == 0


def test_dataset_edits_blocked_new_versions_allowed(tmp_path: Path) -> None:
    env = {"EVALGATE_GUARD_ROOT": str(tmp_path)}
    existing = tmp_path / "evals" / "datasets" / "toys" / "classify.v1.jsonl"
    existing.parent.mkdir(parents=True)
    existing.write_text("")
    (tmp_path / "evals" / "baselines").mkdir(parents=True)
    (tmp_path / "evals" / "baselines" / "classify.json").write_text("{}")

    def guard(payload: dict) -> int:
        return run_hook("pre_tool_guard.py", {**payload, "cwd": str(tmp_path)}, env=env).returncode

    assert guard({"tool_name": "Edit", "tool_input": {"file_path": str(existing)}}) == 2
    assert guard({"tool_name": "MultiEdit", "tool_input": {"file_path": str(existing), "edits": []}}) == 2
    new = existing.with_name("classify.v2.jsonl")
    assert guard({"tool_name": "Write", "tool_input": {"file_path": str(new)}}) == 0
    assert guard({"tool_name": "Write", "tool_input": {"file_path": str(tmp_path / "evals/baselines/new.json")}}) == 0
    for command in [
        "echo '{}' >> evals/datasets/toys/classify.v1.jsonl",
        "echo x > evals/baselines/classify.json",
        "sed -i 's/a/b/' evals/datasets/toys/classify.v1.jsonl",
        "cat x | tee evals/baselines/classify.json",
        "cp /tmp/x evals/baselines/classify.json",
        "mv evals/datasets/toys/classify.v1.jsonl /tmp/x",
        "rm evals/baselines/classify.json",
    ]:
        assert guard({"tool_name": "Bash", "tool_input": {"command": command}}) == 2, command
    for command in [
        "cat evals/datasets/toys/classify.v1.jsonl",
        "cp evals/baselines/classify.json /tmp/copy.json",
        "echo x > evals/datasets/toys/classify.v2.jsonl",
    ]:
        assert guard({"tool_name": "Bash", "tool_input": {"command": command}}) == 0, command


def test_malformed_input_fails_closed() -> None:
    res = subprocess.run(
        [sys.executable, str(HOOKS / "pre_tool_guard.py")],
        input="not json",
        capture_output=True,
        text=True,
        check=False,
    )
    assert res.returncode == 2


def test_env_file_write_blocked() -> None:
    res = run_hook("pre_tool_guard.py", {"tool_name": "Write", "tool_input": {"file_path": str(ROOT / ".env")}})
    assert res.returncode == 2
    ok = run_hook("pre_tool_guard.py", {"tool_name": "Write", "tool_input": {"file_path": str(ROOT / ".env.example")}})
    assert ok.returncode == 0


def test_stop_hook_active_honoured() -> None:
    res = run_hook("stop_check.py", {"stop_hook_active": True}, env={"EVALGATE_STOP_CHECK_CMD": "exit 1"})
    assert res.returncode == 0
    assert res.stdout == ""


def test_stop_hook_blocks_once_on_failure() -> None:
    res = run_hook("stop_check.py", {"stop_hook_active": False}, env={"EVALGATE_STOP_CHECK_CMD": "echo boom; exit 1"})
    assert res.returncode == 0
    out = json.loads(res.stdout)
    assert out["decision"] == "block"
    assert "boom" in out["reason"]
    ok = run_hook("stop_check.py", {}, env={"EVALGATE_STOP_CHECK_CMD": "true"})
    assert ok.stdout == ""


def test_post_edit_format_formats_python(tmp_path: Path) -> None:
    inside = ROOT / ".evalgate" / f"hooktest-{tmp_path.name}"
    inside.mkdir(parents=True, exist_ok=True)
    target = inside / "ugly.py"
    target.write_text("x=1\nimport os\n")
    outside = tmp_path / "ugly.py"
    outside.write_text("x=1\n")
    try:
        res = run_hook("post_edit_format.py", {"tool_name": "Write", "tool_input": {"file_path": str(target)}})
        assert res.returncode == 0
        assert "x = 1" in target.read_text()
        run_hook("post_edit_format.py", {"tool_name": "Write", "tool_input": {"file_path": str(outside)}})
        assert outside.read_text() == "x=1\n"  # files outside the repository are left alone
    finally:
        target.unlink()
        inside.rmdir()
    other = run_hook("post_edit_format.py", {"tool_name": "Write", "tool_input": {"file_path": "README.md"}})
    assert other.returncode == 0


def test_session_start_noop_locally() -> None:
    res = subprocess.run(
        ["bash", str(HOOKS / "session_start.sh")],
        env={**os.environ, "CLAUDE_CODE_REMOTE": "false"},
        capture_output=True,
        text=True,
        check=False,
    )
    assert res.returncode == 0
    assert res.stdout == ""


def test_settings_register_hooks_and_permissions() -> None:
    settings = json.loads((ROOT / ".claude" / "settings.json").read_text())
    assert settings["attribution"] == {"commit": "", "pr": "", "sessionUrl": False}
    hooks = settings["hooks"]
    assert {"SessionStart", "PreToolUse", "PostToolUse", "Stop"} <= set(hooks)
    perms = settings["permissions"]
    for rule in ["Bash(make *)", "Bash(uv run *)", "Bash(git push -u origin *)", "Bash(.tools/bin/*)"]:
        assert rule in perms["allow"]
    for rule in ["Read(./.env)", "Bash(git push --force*)", "Bash(terraform apply*)", "Bash(rm -rf /*)"]:
        assert rule in perms["deny"]
    assert "ask" not in perms
