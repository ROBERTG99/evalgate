"""Markdown report (also the PR comment body). Every number carries its mode (offline or live)."""

from __future__ import annotations

import re
from typing import Any

from evalgate.contracts import CheckResult, Comparison, Report

MARKER = "<!-- evalgate:report -->"
EXCERPT = 200
_MD_SPECIAL = re.compile(r"([\\`*_{}\[\]()#+!|<>~])")


def esc(text: Any, limit: int = EXCERPT) -> str:
    """Escape Markdown and HTML-significant characters and cut to ``limit`` characters."""
    s = " ".join(str(text).split())
    if len(s) > limit:
        s = s[:limit] + "…"
    s = _MD_SPECIAL.sub(r"\\\1", s)
    # Neutralise @mentions and autolinks so target output cannot ping people or link out.
    return s.replace("@", "@\u200b").replace("://", ":\u200b//")


def code(text: Any, limit: int = 80) -> str:
    """Inline code: backslash escapes do not work inside code spans, so backticks and pipes are replaced."""
    s = " ".join(str(text).split())[:limit].replace("`", "'").replace("|", "/")
    return f"`{s}`"


def num(value: float | None, digits: int = 4) -> str:
    return "n/a" if value is None else f"{value:.{digits}f}"


def pp(value: float | None) -> str:
    return "n/a" if value is None else f"{value:+.2f}"


def status(passed: bool) -> str:
    return "✅ pass" if passed else "❌ fail"


def _comparisons(result: CheckResult | None) -> dict[str, Comparison]:
    return {c.metric: c for c in (result.comparisons if result else [])}


def render_markdown(
    report: Report, result: CheckResult | None = None, baseline: Report | None = None, max_cases: int = 10
) -> str:
    ext = report.extensions or {}
    mode = report.mode
    passed = result.passed if result is not None else all(m.passed for m in report.metrics.values())
    comps = _comparisons(result)
    failed_metrics = {f.metric for f in (result.failures if result else [])}
    gates = ext.get("gates") or {}
    lines = [
        MARKER,
        f"## evalgate · {esc(report.suite)} · {status(passed).upper()}",
        "",
        f"Run {code(report.run_id)} · mode **{mode}** · git {code((report.git_sha or 'unknown')[:12])} · "
        f"{report.n_cases} cases · created {esc(report.created_at)}",
    ]
    if result is not None:
        lines.append(
            f"Paired bootstrap: {result.resamples:,} resamples, seed {result.seed}, max regression "
            f"{result.max_regression_pp} pp" + (f", baseline {code(baseline.run_id)}" if baseline else ", no baseline")
        )
    lines += [
        "",
        "| Metric | Value | 95% CI | Threshold | Baseline | Δ (pp) | 95% CI of Δ (pp) | Gate | Mode |",
        "|---|---:|---|---:|---:|---:|---|---|---|",
    ]
    for name, m in report.metrics.items():
        c = comps.get(name)
        gate = "off" if gates.get(name) is False else status(name not in failed_metrics and m.passed)
        lines.append(
            f"| {code(name)} | {num(m.value)} | [{num(m.ci_low)}, {num(m.ci_high)}] | "
            f"{'n/a' if m.threshold is None else ('≥ ' if m.direction == 'higher' else '≤ ') + num(m.threshold, 2)} | "
            f"{num(c.baseline) if c else 'n/a'} | {pp(c.delta_pp) if c else 'n/a'} | "
            f"{f'[{pp(c.ci_low_pp)}, {pp(c.ci_high_pp)}], n={c.n_paired}' if c else 'n/a'} | {gate} | {mode} |"
        )
    budget = ext.get("budget") or {}
    lines += [
        "",
        f"**Cost** USD {report.cost_usd_total:.4f} total, USD {report.cost_usd_per_case:.6f} per case ({mode})"
        + (f", budget USD {budget['max_cost_usd']}" if budget.get("max_cost_usd") is not None else "")
        + f" · **Latency** p50 {report.latency_p50_ms:.0f} ms, p95 {report.latency_p95_ms:.0f} ms ({mode})"
        + (f", budget p95 {budget['max_p95_ms']} ms" if budget.get("max_p95_ms") is not None else ""),
    ]
    if ext.get("run_health") and ext["run_health"] != "ok":
        lines.append(f"**Run health** {esc(ext['run_health'])} (error rate {ext.get('error_rate', 0):.0%})")
    if result is not None and result.failures:
        lines += ["", "### Gate failures", ""]
        for f in result.failures:
            if f.reason == "regression":
                detail = (
                    f"{pp(f.delta_pp)} pp vs baseline (95% CI {pp(f.ci_low_pp)} to {pp(f.ci_high_pp)} pp), "
                    f"{num(f.threshold)} → {num(f.value)} ({mode})"
                )
            else:
                detail = f"value {num(f.value)} vs limit {num(f.threshold)} ({mode})"
            lines.append(f"- **{f.reason}** {code(f.metric)}: {detail}")
    failed_cases = [c for c in report.cases if not c.passed]
    if baseline is not None:
        base_scores = {c.id: c.scores for c in baseline.cases}
        failed_cases.sort(
            key=lambda c: (-sum(base_scores.get(c.id, {}).get(k, 0) - v for k, v in c.scores.items()), c.id)
        )
    if failed_cases:
        lines += [
            "",
            f"### Worst cases ({min(max_cases, len(failed_cases))} of {len(failed_cases)} failed)",
            "",
            "| Case | Scores | Error |",
            "|---|---|---|",
        ]
        for case in failed_cases[:max_cases]:
            scores = ", ".join(f"{esc(k)} {v:.2f}" for k, v in sorted(case.scores.items()))
            lines.append(f"| {code(case.id)} | {scores} | {esc(case.error or '')} |")
    judge = ext.get("judge") or {}
    if judge:
        lines += ["", "### AI judge", ""]
        for name, d in judge.items():
            lines.append(
                f"- {code(name)}: AI judge, rubric {code(d.get('rubric'))}, prompt {code(d.get('prompt_version'))}, "
                f"{int(d.get('position_inconsistent', 0))} position-inconsistent, "
                f"{int(d.get('injections_blocked', 0))} injections blocked, {int(d.get('errors', 0))} errors ({mode})"
            )
        lines.append(
            f"- judge calls {int(ext.get('judge_calls', 0))}, cache hits {int(ext.get('cache_hits', 0))}, "
            f"provider calls {int(ext.get('provider_calls', 0))}; models {esc(', '.join(report.models) or 'none')}"
        )
    lines += ["", f"<sub>evalgate report.v1 · {esc(report.suite)} · mode {mode}</sub>", ""]
    return "\n".join(lines)
