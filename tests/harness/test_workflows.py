"""§17 workflows: present, least privilege, uv cache, Python 3.12/3.13 matrix, no Terraform."""

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github" / "workflows"
REQUIRED = {"ci", "e2e", "evals", "docker", "codeql", "action-selftest", "release"}


def load(name: str) -> dict:
    data = yaml.safe_load((WORKFLOWS / f"{name}.yml").read_text())
    data["on"] = data.pop(True, data.get("on"))  # YAML 1.1 reads the key `on` as True
    return data


def steps(workflow: dict) -> list[dict]:
    return [step for job in workflow["jobs"].values() for step in job.get("steps", [])]


def test_required_workflows_present() -> None:
    present = {p.stem for p in WORKFLOWS.glob("*.yml")}
    assert present >= REQUIRED, REQUIRED - present
    assert not [p for p in present if "terraform" in p]
    for name in present:
        workflow = load(name)
        assert workflow["permissions"] == {"contents": "read"} or name == "release", name
        for job in workflow["jobs"].values():
            assert "timeout-minutes" in job, name


def test_ci_matrix_and_cache() -> None:
    ci = load("ci")
    assert ci["jobs"]["test"]["strategy"]["matrix"]["python"] == ["3.12", "3.13"]
    uv_steps = [s for s in steps(ci) if str(s.get("uses", "")).startswith("astral-sh/setup-uv")]
    assert uv_steps and all(s["with"]["enable-cache"] is True for s in uv_steps)
    runs = "\n".join(str(s.get("run", "")) for s in steps(ci))
    for needle in ("make lint", "make typecheck", "make test", "make build", "tests/harness/test_hooks.py"):
        assert needle in runs, needle


def test_docker_scans_fail_on_high_and_critical() -> None:
    runs = "\n".join(str(s.get("run", "")) for s in steps(load("docker")))
    assert "hadolint" in runs
    assert "--severity HIGH,CRITICAL" in runs and "--exit-code 1" in runs


def test_release_only_on_tags_with_trusted_publishing() -> None:
    release = load("release")
    assert release["on"]["push"]["tags"] == ["v*"]
    publish = release["jobs"]["pypi"]
    assert publish["permissions"]["id-token"] == "write"
    assert any(str(s.get("uses", "")).startswith("pypa/gh-action-pypi-publish") for s in publish["steps"])


def test_actions_are_pinned_to_commit_shas() -> None:
    """Supply chain: a moved tag must not change what runs in CI or in the publish job."""
    files = [*WORKFLOWS.glob("*.yml"), ROOT / "action" / "action.yml"]
    for path in files:
        for line in path.read_text().splitlines():
            ref = line.strip().removeprefix("- ").removeprefix("uses:").strip() if "uses:" in line else None
            if ref is None or ref.startswith("./"):
                continue
            assert re.fullmatch(r"[\w.-]+/[\w./-]+@[0-9a-f]{40}( # \S+)?", ref), f"{path.name}: {ref}"
