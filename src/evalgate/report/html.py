"""Self-contained HTML report: one file, inline CSS from the viewer tokens, no scripts."""

from __future__ import annotations

from importlib import resources

from jinja2 import Environment, PackageLoader, select_autoescape

from evalgate.contracts import CheckResult, Report


def _css() -> str:
    static = resources.files("evalgate.viewer").joinpath("static")
    return static.joinpath("tokens.css").read_text(encoding="utf-8") + static.joinpath("app.css").read_text(
        encoding="utf-8"
    )


def render_html(report: Report, result: CheckResult | None = None, baseline: Report | None = None) -> str:
    env = Environment(
        loader=PackageLoader("evalgate.report", "templates"), autoescape=select_autoescape(["html", "j2"])
    )
    passed = result.passed if result is not None else all(m.passed for m in report.metrics.values())
    failed = {f.metric: f.reason for f in (result.failures if result else [])}
    cases = sorted(report.cases, key=lambda c: (c.passed, c.id))
    return env.get_template("report.html.j2").render(
        report=report,
        result=result,
        baseline=baseline,
        passed=passed,
        failed=failed,
        comps={c.metric: c for c in (result.comparisons if result else [])},
        gates=(report.extensions or {}).get("gates") or {},
        cases=cases,
        css=_css(),
    )
