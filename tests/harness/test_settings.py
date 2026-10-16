import json
from pathlib import Path


def test_attribution_key_empty(root: Path) -> None:
    settings = json.loads((root / ".claude/settings.json").read_text())
    assert settings["attribution"] == {"commit": "", "pr": "", "sessionUrl": False}
    rule = (root / ".claude/rules/git-commits.md").read_text()
    assert not rule.startswith("---"), "git-commits rule must have no frontmatter"
    assert "Co-Authored-By" in rule
    assert "GIT_AUTHOR_" in rule
