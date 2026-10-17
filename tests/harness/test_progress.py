import re
from pathlib import Path


def test_every_spec_task_listed(root: Path) -> None:
    spec_path = root / "BUILD.md"
    if not spec_path.exists():
        spec_path = root / "docs/specs/000-build-spec.md"
    spec = spec_path.read_text()
    tasks = re.findall(r"\*\*(T-\d+) · ", spec)
    assert len(tasks) == 46
    progress = (root / "PROGRESS.md").read_text()
    assert progress.index("## Needs the maintainer") < progress.index("## Tasks")
    for task in tasks:
        assert re.search(rf"^\| {task} \|", progress, re.M), task
    assert "## Global Definition of Done" in progress
    for doc in ["docs/DECISIONS.md", "docs/KNOWN_LIMITATIONS.md"]:
        assert (root / doc).exists()
