"""Plain-text rendering of check results (CLI output)."""

from __future__ import annotations

from evalgate.contracts import CheckResult, Report


def fmt_pp(value: float | None) -> str:
    return "n/a" if value is None else f"{value:+.2f} pp"


def render_check_text(result: CheckResult, report: Report) -> str:
    lines = [
        f"evalgate check: {'PASS' if result.passed else 'FAIL'} — suite {report.suite}, run {report.run_id}, "
        f"mode {report.mode}",
        f"  seed {result.seed}, {result.resamples} paired-bootstrap resamples, max regression "
        f"{result.max_regression_pp} pp",
    ]
    for name, m in report.metrics.items():
        threshold = "" if m.threshold is None else f" threshold {m.threshold}"
        missed = "below" if m.direction == "higher" else "above"
        lines.append(f"  metric {name}: {m.value:.4f}{threshold} ({'ok' if m.passed else missed})")
    for c in result.comparisons:
        lines.append(
            f"  delta {c.metric}: {c.baseline:.4f} -> {c.candidate:.4f} = {fmt_pp(c.delta_pp)} "
            f"[95% CI {fmt_pp(c.ci_low_pp)}, {fmt_pp(c.ci_high_pp)}], n={c.n_paired}"
        )
    lines.append(
        f"  cost USD {report.cost_usd_total:.4f}, latency p50 {report.latency_p50_ms:.0f} ms, "
        f"p95 {report.latency_p95_ms:.0f} ms"
    )
    for f in result.failures:
        if f.reason == "regression":
            detail = f"{fmt_pp(f.delta_pp)} [95% CI {fmt_pp(f.ci_low_pp)}, {fmt_pp(f.ci_high_pp)}]"
        else:
            detail = f"value {f.value} vs threshold {f.threshold}"
        lines.append(f"  FAILED {f.reason}: {f.metric} {detail}")
    return "\n".join(lines)
