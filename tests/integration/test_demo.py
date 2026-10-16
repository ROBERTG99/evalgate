"""`make demo`: the v2 candidate fails the gate (exit 1); switching to v1 passes it (exit 0)."""

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def run_demo(toys_url: str, tmp_path: Path) -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        "EVALGATE_TOYS_URL": toys_url,
        "EVALGATE_HTTP_ALLOWED_HOSTS": "127.0.0.1,localhost",
        "EVALGATE": f"{sys.executable} -m evalgate.cli",
        "EVALGATE_DEMO_DIR": str(tmp_path / "demo"),
        "EVALGATE_HOME": str(tmp_path / "home"),
        "EVALGATE_LLM_PROVIDER": "fake",
        "NO_COLOR": "1",
    }
    return subprocess.run(
        ["bash", "scripts/demo.sh"], cwd=ROOT, env=env, capture_output=True, text=True, timeout=300, check=False
    )


def test_demo_fails_then_passes(toys_url: str, tmp_path: Path) -> None:
    out = run_demo(toys_url, tmp_path)
    assert out.returncode == 0, out.stdout + out.stderr
    text = out.stdout
    fail_at = text.index("evalgate check exited 1")
    pass_at = text.index("evalgate check exited 0")
    assert fail_at < pass_at
    assert "regression" in text[:pass_at]
    assert (tmp_path / "demo" / "classify-v2.json").exists()
    assert (tmp_path / "demo" / "classify-v1.json").exists()


def test_transcript_matches_the_script() -> None:
    transcript = (ROOT / "docs" / "demo-transcript.txt").read_text()
    assert "evalgate check exited 1" in transcript
    assert "evalgate check exited 0" in transcript
    assert transcript.index("exited 1") < transcript.index("exited 0")
