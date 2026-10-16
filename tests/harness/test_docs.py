"""§18 documentation deliverables and the README's number citations."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

REQUIRED = [
    "README.md",
    "CONTRIBUTING.md",
    "SECURITY.md",
    "CHANGELOG.md",
    "LICENSE",
    "evals/REPORT.md",
    "docs/architecture.md",
    "docs/ai-development.md",
    "docs/evaluation.md",
    "docs/security.md",
    "docs/runbook.md",
    "docs/DEVELOPMENT.md",
    "docs/KNOWN_LIMITATIONS.md",
    "docs/DECISIONS.md",
    "docs/design-faq.md",
    *(f"docs/contracts/{name}.md" for name in ("suite", "report", "check", "rubric", "cassette", "action")),
]
ADRS = ["0001", "0002", "0003", "0004", "0005", "0006", "0007"]
CITATION = re.compile(r"evals/reports/|evals/REPORT\.md|docs/demo-transcript\.txt|`make [a-z-]+`")


def section(text: str, heading: str) -> str:
    start = text.index(f"\n## {heading}\n")
    end = text.find("\n## ", start + 1)
    return text[start : end if end != -1 else None]


def test_required_docs_exist() -> None:
    missing = [p for p in REQUIRED if not (ROOT / p).is_file() or not (ROOT / p).read_text().strip()]
    assert not missing, missing
    for number in ADRS:
        adrs = list((ROOT / "docs" / "adr").glob(f"{number}-*.md"))
        assert len(adrs) == 1, number
        text = adrs[0].read_text()
        assert "Alternatives" in text or "Rejected" in text, adrs[0].name
    faq = (ROOT / "docs" / "design-faq.md").read_text()
    questions = re.findall(r"^## (\d+)\. ", faq, flags=re.M)
    assert questions == [str(i) for i in range(1, 16)]
    for block in re.split(r"^## \d+\. ", faq, flags=re.M)[1:]:
        assert re.search(r"[\w/.-]+\.(py|ya?ml|sql|json|md)(:|#L)\d+", block), block[:80]


def test_readme_numbers_cite_reports() -> None:
    results = section((ROOT / "README.md").read_text(), "Results")
    rows = [line for line in results.splitlines() if line.startswith("|") and not line.startswith("|---")][1:]
    assert len(rows) >= 10
    for row in rows:
        if re.search(r"\d", row):
            assert CITATION.search(row), row
    assert "live evals were not run" in results or "live" in results.lower()


def test_runbook_has_alert_anchors() -> None:
    runbook = (ROOT / "docs" / "runbook.md").read_text()
    alerts = (ROOT / "deploy" / "prometheus" / "alerts.yml").read_text()
    for anchor in re.findall(r"docs/runbook\.md#([a-z0-9-]+)", alerts):
        headings = [
            re.sub(r"[^a-z0-9 -]", "", h.lower()).replace(" ", "-") for h in re.findall(r"^#+ (.+)$", runbook, re.M)
        ]
        assert anchor in headings, anchor


def test_relative_links_resolve() -> None:
    docs = [ROOT / "README.md", ROOT / "CONTRIBUTING.md", ROOT / "SECURITY.md", *(ROOT / "docs").rglob("*.md")]
    broken = []
    for doc in docs:
        if "specs" in doc.parts:
            continue
        for target in re.findall(r"\]\(([^)#\s]+)(?:#[^)]*)?\)", doc.read_text()):
            if re.match(r"[a-z]+:", target):
                continue
            if "evals/reports/" in target or target.startswith("reports/"):
                continue  # generated, gitignored
            if not (doc.parent / target).exists():
                broken.append(f"{doc.relative_to(ROOT)} -> {target}")
    assert not broken, broken
