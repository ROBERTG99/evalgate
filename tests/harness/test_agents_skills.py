import json
import re
from pathlib import Path

import yaml

AGENTS = ["reviewer", "security-auditor", "test-designer", "eval-analyst", "ux-reviewer", "docs-editor",
          "stats-reviewer"]
SKILLS = ["tdd", "quality-gate", "eval-report", "new-adr", "add-migration", "add-endpoint", "add-eval-case",
          "demo-capture", "release", "add-metric", "calibrate-judge", "add-target-adapter"]


def frontmatter(path: Path) -> tuple[dict, str]:
    text = path.read_text()
    assert text.startswith("---\n"), path
    _, fm, body = text.split("---\n", 2)
    return yaml.safe_load(fm), body


def test_frontmatter_and_steps(root: Path) -> None:
    for name in AGENTS:
        fm, body = frontmatter(root / ".claude/agents" / f"{name}.md")
        assert set(fm) == {"name", "description", "tools", "model"}, name
        assert fm["name"] == name
        assert len(body.strip().splitlines()) >= 20
    reviewer_fm, reviewer_body = frontmatter(root / ".claude/agents/reviewer.md")
    assert "Write" not in reviewer_fm["tools"] and "Edit" not in reviewer_fm["tools"]
    assert "Verdict: ship" in reviewer_body and "Verdict: fix first" in reviewer_body
    for name in SKILLS:
        fm, body = frontmatter(root / ".claude/skills" / name / "SKILL.md")
        assert fm["name"] == name
        assert fm["description"]
        assert "## Steps" in body
        steps = re.findall(r"^\d+\. ", body.split("## Steps", 1)[1], re.M)
        assert len(steps) >= 4, name


def test_mcp_and_integrations(root: Path) -> None:
    mcp = json.loads((root / ".mcp.json").read_text())
    assert {"playwright", "duckdb"} <= set(mcp["mcpServers"])
    assert "--read-only" in mcp["mcpServers"]["duckdb"]["args"]
    assert (root / "CODEOWNERS").read_text().strip() == "* @ROBERTG99"
    dependabot = yaml.safe_load((root / ".github/dependabot.yml").read_text())
    ecosystems = {u["package-ecosystem"] for u in dependabot["updates"]}
    assert ecosystems == {"pip", "github-actions", "docker"}
    for path in [".pre-commit-config.yaml", ".devcontainer/devcontainer.json", ".github/pull_request_template.md",
                 ".github/ISSUE_TEMPLATE/bug_report.md"]:
        assert (root / path).exists(), path
