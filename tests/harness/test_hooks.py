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
        "make check-fast",
        "uv run pytest tests/unit",
    ],
)
def test_allowed_bash_passes(command: str) -> None:
    assert bash(command).returncode == 0, command


def test_dataset_edits_blocked_new_versions_allowed(tmp_path: Path) -> None:
    existing = ROOT / "evals" / "datasets" / "toys" / "classify.v1.jsonl"
    existing.parent.mkdir(parents=True, exist_ok=True)
    created = not existing.exists()
    if created:
        existing.write_text("")
    try:
        edit = run_hook("pre_tool_guard.py", {"tool_name": "Edit", "tool_input": {"file_path": str(existing)}})
        assert edit.returncode == 2
        new = existing.with_name("classify.v99.jsonl")
        write = run_hook("pre_tool_guard.py", {"tool_name": "Write", "tool_input": {"file_path": str(new)}})
        assert write.returncode == 0
        baseline = ROOT / "evals" / "baselines" / "brand-new.json"
        assert not baseline.exists()
        ok = run_hook("pre_tool_guard.py", {"tool_name": "Write", "tool_input": {"file_path": str(baseline)}})
        assert ok.returncode == 0
    finally:
        if created:
            existing.unlink()


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
    target = tmp_path / "ugly.py"
    target.write_text("x=1\nimport os\n")
    res = run_hook("post_edit_format.py", {"tool_name": "Write", "tool_input": {"file_path": str(target)}})
    assert res.returncode == 0
    assert "x = 1" in target.read_text()
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
