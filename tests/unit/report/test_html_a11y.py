import re

from evalgate.report.html import render_html
from evalgate.stats.gate import check
from tests.factories import make_report


def test_scrollable_tables_are_keyboard_focusable_regions() -> None:
    """WCAG 2.1.1: a horizontally scrolling table must be reachable by keyboard (axe scrollable-region-focusable)."""
    base = make_report({"acc": [1.0] * 20})
    cand = make_report({"acc": [0.0] * 5 + [1.0] * 15})
    page = render_html(cand, check(cand, report_sha256="x", baseline=base, resamples=100), base)
    wraps = re.findall(r'<div class="table-wrap"[^>]*>', page)
    assert len(wraps) == 2
    for tag in wraps:
        assert 'tabindex="0"' in tag and 'role="region"' in tag
        assert re.search(r'aria-label="[^"]+\(scrolls horizontally\)"', tag)


def test_footer_does_not_claim_offline_for_live_reports() -> None:
    report = make_report({"acc": [1.0] * 10}).model_copy(update={"mode": "live"})
    page = render_html(report, check(report, report_sha256="x", resamples=100), None)
    assert "generated offline" not in page
