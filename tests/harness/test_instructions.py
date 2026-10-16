import re
from pathlib import Path

RULES = ["git-commits", "python", "frontend", "llm-code", "testing", "evals", "statistics",
         "docker", "security", "docs"]


def test_claude_md_short_and_targets_exist(root: Path) -> None:
    claude = (root / "CLAUDE.md").read_text()
    assert len(claude.splitlines()) < 200
    makefile = (root / "Makefile").read_text()
    targets = set(re.findall(r"^([a-z][a-z-]*):", makefile, re.M))
    mentioned = set(re.findall(r"`make ([a-z-]+)`", claude))
    assert len(mentioned) >= 20
    assert mentioned <= targets, mentioned - targets
    assert "Co-Authored-By" in claude
    assert "PROGRESS.md" in claude and "docs/DECISIONS.md" in claude
    agents = (root / "AGENTS.md").read_text()
    assert "make check-fast" in agents and "Co-Authored-By" in agents


def test_rules_frontmatter(root: Path) -> None:
    for name in RULES:
        text = (root / ".claude/rules" / f"{name}.md").read_text()
        if name == "git-commits":
            assert not text.startswith("---")
        else:
            assert text.startswith("---\npaths:\n"), name
