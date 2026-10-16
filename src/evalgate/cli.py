"""The ``evalgate`` command line. Exit codes: 0 ok, 1 gate failed, 2 invalid input, 3 budget abort,
4 internal error, 5 strict export failure."""

from __future__ import annotations

import functools
import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import Annotated, Any, Literal

import typer

from evalgate import __version__
from evalgate.errors import (
    EXIT_GATE_FAILED,
    EXIT_INTERNAL,
    EvalgateError,
)

app = typer.Typer(
    name="evalgate",
    help="Golden sets, deterministic metrics and calibrated LLM judges as a CI gate.",
    no_args_is_help=True,
    add_completion=False,
    pretty_exceptions_enable=False,
    rich_markup_mode=None,
)
import_app = typer.Typer(help="Import suites from other eval tools.", no_args_is_help=True, rich_markup_mode=None)
export_app = typer.Typer(help="Export reports to observability tools.", no_args_is_help=True, rich_markup_mode=None)
app.add_typer(import_app, name="import")
app.add_typer(export_app, name="export")


def err(message: str) -> None:
    typer.echo(message, err=True)


def handle_errors[F: Callable[..., Any]](fn: F) -> F:
    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return fn(*args, **kwargs)
        except typer.Exit:
            raise
        except EvalgateError as exc:
            err(f"evalgate: {exc}")
            raise typer.Exit(exc.exit_code) from exc
        except KeyboardInterrupt:
            raise
        except Exception as exc:
            err(f"evalgate: internal error: {exc.__class__.__name__}: {exc}")
            if os.environ.get("EVALGATE_DEBUG"):
                raise
            raise typer.Exit(EXIT_INTERNAL) from exc

    return wrapper  # type: ignore[return-value]


def version_callback(value: bool) -> None:
    if value:
        typer.echo(f"evalgate {__version__}")
        raise typer.Exit(0)


@app.callback()
def main_callback(
    version: Annotated[
        bool, typer.Option("--version", callback=version_callback, is_eager=True, help="Show the version.")
    ] = False,
) -> None:
    from evalgate.telemetry import configure_logging

    configure_logging()


# run ------------------------------------------------------------------------------------------
@app.command()
@handle_errors
def run(
    suite: Annotated[Path, typer.Argument(help="Suite YAML (schema evalgate.suite.v1).")],
    out: Annotated[Path, typer.Option("--out", help="Where to write the report.v1 JSON.")],
    split: Annotated[str, typer.Option("--split", help="dev or test.")] = "test",
    cache: Annotated[str, typer.Option("--cache", help="rw, ro or off.")] = "rw",
    cache_targets: Annotated[bool, typer.Option("--cache-targets", help="Also cache target responses.")] = False,
    resume: Annotated[str | None, typer.Option("--resume", help="Resume a run id; stored cases are skipped.")] = None,
    otel: Annotated[bool, typer.Option("--otel", help="Emit OpenTelemetry spans.")] = False,
) -> None:
    """Run a suite against its target and write a report."""
    from evalgate.errors import InvalidInputError
    from evalgate.report.build import write_report
    from evalgate.runner import RunOptions, run_suite
    from evalgate.stats.gate import sha256_file
    from evalgate.suite import load_suite

    if split not in ("dev", "test"):
        raise InvalidInputError("--split", "", f"split must be dev or test, not {split!r}")
    if cache not in ("rw", "ro", "off"):
        raise InvalidInputError("--cache", "", f"cache must be rw, ro or off, not {cache!r}")
    loaded = load_suite(suite, split=split)
    cache_mode: Literal["rw", "ro", "off"] = cache  # type: ignore[assignment]
    result = run_suite(
        loaded,
        RunOptions(split=split, cache_mode=cache_mode, cache_targets=cache_targets, resume=resume, otel=otel),
    )
    path = write_report(result.report, out)
    if result.store_error is None:
        _record_report_path(result.report.run_id, path, sha256_file(path))
    r = result.report
    ext = r.extensions or {}
    err(
        f"evalgate: {r.suite} [{split}] run {r.run_id}: {r.n_cases} cases, mode {r.mode}, "
        f"cost USD {r.cost_usd_total:.4f}, p95 {r.latency_p95_ms:.0f} ms, health {ext.get('run_health')}"
    )
    for name, m in r.metrics.items():
        mark = "pass" if m.passed else "FAIL"
        threshold = "" if m.threshold is None else f" (threshold {m.threshold})"
        err(f"  {mark}  {name} = {m.value:.4f} [{m.ci_low:.4f}, {m.ci_high:.4f}]{threshold}")
    if "judge_calls" in ext:
        err(
            f"  judge calls {ext['judge_calls']}, cache hits {ext['cache_hits']}, "
            f"provider calls {ext['provider_calls']}"
        )
    err(f"  report: {path}")


def _record_report_path(run_id: str, path: Path, digest: str) -> None:
    from evalgate import config
    from evalgate.store import RunStore

    try:
        store = RunStore(config.home() / "runs.duckdb")
        try:
            store.set_report_path(run_id, str(path), digest)
        finally:
            store.close()
    except Exception as exc:  # the store is optional
        err(f"evalgate: warning: run store not updated: {exc}")


# check ----------------------------------------------------------------------------------------
@app.command()
@handle_errors
def check(
    report: Annotated[Path, typer.Argument(help="Candidate report.v1 JSON.")],
    baseline: Annotated[Path | None, typer.Option("--baseline", help="Baseline report.v1 JSON.")] = None,
    max_regression_pp: Annotated[float, typer.Option("--max-regression-pp", help="Allowed drop, in pp.")] = 1.0,
    out_json: Annotated[Path | None, typer.Option("--out-json", help="Write check.v1 JSON here.")] = None,
    fmt: Annotated[str, typer.Option("--format", help="text, json or github.")] = "text",
) -> None:
    """Gate a report on thresholds, budgets and (with a baseline) paired-bootstrap regressions."""
    from evalgate import config, telemetry
    from evalgate.errors import InvalidInputError
    from evalgate.report.build import load_report
    from evalgate.report.render import render_check_text
    from evalgate.stats.gate import check as run_check
    from evalgate.stats.gate import sha256_file

    if fmt not in ("text", "json", "github"):
        raise InvalidInputError("--format", "", f"format must be text, json or github, not {fmt!r}")
    if max_regression_pp < 0:
        raise InvalidInputError("--max-regression-pp", "", "must be >= 0")
    cand = load_report(report)
    base = load_report(baseline) if baseline else None
    result = run_check(
        cand,
        report_sha256=sha256_file(report),
        baseline=base,
        baseline_sha256=sha256_file(baseline) if baseline else None,
        max_regression_pp=max_regression_pp,
        seed=config.bootstrap_seed(),
    )
    payload = result.model_dump(mode="json", by_alias=True)
    if out_json:
        out_json.parent.mkdir(parents=True, exist_ok=True)
        out_json.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    if fmt == "json":
        typer.echo(json.dumps(payload, indent=2))
    elif fmt == "github":
        for f in result.failures:
            typer.echo(f"::error title=evalgate {f.reason}::{f.metric}: {_failure_text(f)}")
        typer.echo(render_check_text(result, cand))
    else:
        typer.echo(render_check_text(result, cand))
    telemetry.count("evalgate_gate_decisions_total", decision="pass" if result.passed else "fail")
    _audit(result, cand.git_sha)
    if not result.passed:
        raise typer.Exit(EXIT_GATE_FAILED)


def _failure_text(f: Any) -> str:
    if f.reason == "regression":
        return f"delta {f.delta_pp:+.2f} pp, 95% CI [{f.ci_low_pp:+.2f}, {f.ci_high_pp:+.2f}]"
    return f"value {f.value} vs threshold {f.threshold}"


def _audit(result: Any, git_sha: str | None) -> None:
    from evalgate import config
    from evalgate.store import RunStore

    try:
        store = RunStore(config.home() / "runs.duckdb")
        try:
            store.audit_append(
                report_sha256=result.report_sha256,
                baseline_sha256=result.baseline_sha256,
                git_sha=git_sha,
                decision="pass" if result.passed else "fail",
                failures=[f.model_dump(mode="json") for f in result.failures],
                actor=os.environ.get("GITHUB_ACTOR") or os.environ.get("USER"),
            )
        finally:
            store.close()
    except Exception as exc:
        err(f"evalgate: warning: gate audit not written: {exc}")


# report ---------------------------------------------------------------------------------------
@app.command()
@handle_errors
def report(
    report_path: Annotated[Path, typer.Argument(metavar="REPORT", help="report.v1 JSON.")],
    md: Annotated[Path, typer.Option("--md", help="Markdown output path.")],
    html: Annotated[Path | None, typer.Option("--html", help="Self-contained HTML output path.")] = None,
    baseline: Annotated[Path | None, typer.Option("--baseline", help="Baseline report for deltas.")] = None,
    max_regression_pp: Annotated[float, typer.Option("--max-regression-pp")] = 1.0,
) -> None:
    """Render Markdown (and optionally HTML) from a report."""
    from evalgate import config
    from evalgate.report.build import load_report
    from evalgate.report.html import render_html
    from evalgate.report.markdown import render_markdown
    from evalgate.stats.gate import check as run_check
    from evalgate.stats.gate import sha256_file

    cand = load_report(report_path)
    base = load_report(baseline) if baseline else None
    result = run_check(
        cand,
        report_sha256=sha256_file(report_path),
        baseline=base,
        baseline_sha256=sha256_file(baseline) if baseline else None,
        max_regression_pp=max_regression_pp,
        seed=config.bootstrap_seed(),
    )
    md.parent.mkdir(parents=True, exist_ok=True)
    md.write_text(render_markdown(cand, result, baseline=base), encoding="utf-8")
    if html:
        html.parent.mkdir(parents=True, exist_ok=True)
        html.write_text(render_html(cand, result, baseline=base), encoding="utf-8")
    err(f"evalgate: wrote {md}" + (f" and {html}" if html else ""))


# calibrate ------------------------------------------------------------------------------------
@app.command()
@handle_errors
def calibrate(
    rubric: Annotated[Path, typer.Option("--rubric", help="Rubric YAML (schema evalgate.rubric.v1).")],
    labels: Annotated[Path, typer.Option("--labels", help="Label rows JSONL.")],
    split: Annotated[str, typer.Option("--split", help="Label split to score: test (adoption) or dev.")] = "test",
    out: Annotated[Path | None, typer.Option("--out", help="Write the calibration JSON here.")] = None,
) -> None:
    """Measure a judge against labels: agreement, Cohen's kappa, confusion, position and verbosity bias."""
    from evalgate.judge.calibrate import calibrate as run_calibrate
    from evalgate.judge.calibrate import render_calibration

    result = run_calibrate(rubric, labels, split=split)
    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    typer.echo(render_calibration(result))
    if not result["passed"]:
        raise typer.Exit(EXIT_GATE_FAILED)


# serve ----------------------------------------------------------------------------------------
@app.command()
@handle_errors
def serve(
    reports_dir: Annotated[Path, typer.Argument(help="Directory of report.v1 JSON files.")],
    port: Annotated[int, typer.Option("--port", help="TCP port.")] = 8100,
    host: Annotated[str, typer.Option("--host", help="Bind address (127.0.0.1 by default).")] = "127.0.0.1",
) -> None:
    """Serve the read-only report viewer."""
    from evalgate.viewer.server import serve as run_server

    run_server(reports_dir, host=host, port=port)


# import ---------------------------------------------------------------------------------------
@import_app.command("promptfoo")
@handle_errors
def import_promptfoo(
    config_path: Annotated[Path, typer.Argument(metavar="CONFIG", help="promptfooconfig.yaml")],
    out_dir: Annotated[Path, typer.Option("--out-dir", help="Where to write suite and dataset.")] = Path("."),
    name: Annotated[str | None, typer.Option("--name", help="Suite name.")] = None,
    base_url: Annotated[
        str | None, typer.Option("--base-url", help="Replace scheme and host of the provider URL.")
    ] = None,
) -> None:
    """Convert a Promptfoo config into an evalgate suite and dataset."""
    from evalgate.adapters.promptfoo import import_promptfoo as run_import

    suite_path, dataset_path, unsupported = run_import(config_path, out_dir, name=name, base_url=base_url)
    err(f"evalgate: wrote {suite_path} and {dataset_path}")
    if unsupported:
        err(f"evalgate: unsupported asserts listed in meta.unsupported_asserts: {', '.join(sorted(set(unsupported)))}")


# export ---------------------------------------------------------------------------------------
@export_app.command("langfuse")
@handle_errors
def export_langfuse(
    report_path: Annotated[Path, typer.Argument(metavar="REPORT", help="report.v1 JSON.")],
    strict: Annotated[bool, typer.Option("--strict", help="Exit 5 when the export fails.")] = False,
    host: Annotated[str | None, typer.Option("--host", help="Langfuse host (default LANGFUSE_HOST).")] = None,
) -> None:
    """Send one trace per case and one score per metric to Langfuse."""
    from evalgate.errors import StrictExportError
    from evalgate.export.langfuse import LangfuseExporter
    from evalgate.report.build import load_report

    rep = load_report(report_path)
    exporter = LangfuseExporter.from_env(host=host)
    outcome = exporter.export(rep)
    if outcome.ok:
        err(f"evalgate: exported {outcome.traces} traces and {outcome.scores} scores to {exporter.host}")
        return
    if strict:
        raise StrictExportError(f"langfuse export failed: {outcome.error}")
    err(f"evalgate: warning: langfuse export failed, continuing: {outcome.error}")


# gc -------------------------------------------------------------------------------------------
@app.command()
@handle_errors
def gc(
    keep_days: Annotated[int, typer.Option("--keep-days", help="Keep runs newer than this.")] = 30,
    verify_audit: Annotated[bool, typer.Option("--verify-audit", help="Verify the gate audit hash chain.")] = False,
) -> None:
    """Prune old runs, audit rows (365 days) and cache rows (EVALGATE_CACHE_TTL_DAYS)."""
    from evalgate import config
    from evalgate.cache import ResponseCache
    from evalgate.store import RunStore

    home = config.home()
    store = RunStore(home / "runs.duckdb")
    try:
        if verify_audit:
            ok, bad = store.verify_audit()
            if not ok:
                err(f"evalgate: gate audit chain broken at seq {bad}")
                raise typer.Exit(EXIT_GATE_FAILED)
            err("evalgate: gate audit chain verified")
        pruned = store.gc(keep_days=keep_days)
    finally:
        store.close()
    cache_pruned = 0
    if (home / "cache.duckdb").exists():
        cache = ResponseCache(home / "cache.duckdb", mode="rw")
        try:
            cache_pruned = cache.gc(config.cache_ttl_days())
        finally:
            cache.close()
    err(f"evalgate: pruned {pruned['runs']} runs, {pruned['audit']} audit rows, {cache_pruned} cache rows")


# schema ---------------------------------------------------------------------------------------
@app.command()
@handle_errors
def schema(
    name: Annotated[str, typer.Argument(help="suite, report, check, rubric or cassette (also dataset, label).")],
) -> None:
    """Print a JSON Schema."""
    from evalgate.contracts import SHORT_NAMES, json_schema
    from evalgate.errors import InvalidInputError

    if name not in SHORT_NAMES:
        raise InvalidInputError(name, "", f"unknown schema; choose one of {', '.join(SHORT_NAMES)}")
    typer.echo(json.dumps(json_schema(SHORT_NAMES[name]), indent=2))


def main() -> None:
    app()


if __name__ == "__main__":  # pragma: no cover
    main()
