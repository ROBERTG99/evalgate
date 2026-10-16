import os
import re
from pathlib import Path

from evalgate.report.html import render_html
from evalgate.report.markdown import MARKER, esc, render_markdown
from evalgate.stats.gate import check
from tests.factories import make_report

GOLDEN = Path(__file__).resolve().parents[2] / "fixtures" / "golden"


def fixture_pair():  # type: ignore[no-untyped-def]
    base_vals = [1.0] * 54 + [0.0] * 6
    cand_vals = [0.0] * 8 + [1.0] * 46 + [0.0] * 6
    ext = {
        "gates": {"label_accuracy": True, "label_format": False},
        "budget": {"max_cost_usd": 0.5, "max_p95_ms": 800},
        "run_health": "ok",
    }
    baseline = make_report(
        {"label_accuracy": base_vals, "label_format": [1.0] * 60},
        suite="classify",
        threshold=0.9,
        extensions=ext,
        seed=1,
        cost=0.0042,
    )
    candidate = make_report(
        {"label_accuracy": cand_vals, "label_format": [1.0] * 60},
        suite="classify",
        threshold=0.9,
        extensions=ext,
        seed=2,
        cost=0.0042,
    )
    result = check(candidate, report_sha256="c" * 64, baseline=baseline, baseline_sha256="b" * 64, seed=1337)
    return candidate, result, baseline


def check_golden(name: str, text: str) -> None:
    path = GOLDEN / name
    if os.environ.get("UPDATE_GOLDEN") == "1":
        path.write_text(text)
    assert text == path.read_text(), f"golden {name} differs; inspect and rerun with UPDATE_GOLDEN=1 if intended"


def test_golden_report_md() -> None:
    candidate, result, baseline = fixture_pair()
    assert not result.passed
    md = render_markdown(candidate, result, baseline=baseline)
    assert md.startswith(MARKER)
    check_golden("report.md", md)


def test_golden_report_html() -> None:
    candidate, result, baseline = fixture_pair()
    html = render_html(candidate, result, baseline=baseline)
    assert "<script" not in html  # self-contained, no JavaScript
    assert ':root[data-theme="dark"]' in html  # trusted package CSS is inlined unescaped
    assert "&#34;" not in html.split("</style>")[0]
    assert "http://" not in html and "https://" not in html  # no external resources
    check_golden("report.html", html)


def test_mode_label_per_number() -> None:
    candidate, result, baseline = fixture_pair()
    md = render_markdown(candidate, result, baseline=baseline)
    rows = [line for line in md.splitlines() if line.startswith("| `")]
    metric_rows = [r for r in rows if r.startswith("| `label")]
    assert metric_rows
    for row in metric_rows:
        assert row.rstrip().endswith("| offline |")
    for line in md.splitlines():
        if line.startswith(("**Cost**", "- **")) and re.search(r"\d", line):
            assert "(offline)" in line, line
    live = candidate.model_copy(update={"mode": "live"})
    assert "| live |" in render_markdown(live, result)


def test_markdown_escapes_and_truncates() -> None:
    assert esc("a|b *c* <script>") == "a\\|b \\*c\\* \\<script\\>"
    assert len(esc("x" * 500)) == 201


def test_mentions_and_links_neutralised() -> None:
    out = esc("ping @org/team and see https://evil.example")
    assert "@org" not in out
    assert "https://" not in out
