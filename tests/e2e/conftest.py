"""E2E fixtures: the viewer URL (``EVALGATE_VIEWER_URL`` for the running stack, else a local seeded viewer)."""

from __future__ import annotations

import os
import shutil
from collections.abc import Iterator
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _seed(reports: Path, toys_url: str) -> None:
    from evalgate.report.build import write_report
    from evalgate.runner import RunOptions, run_suite
    from evalgate.suite import load_suite

    for suite in ("classify", "extract", "answer"):
        shutil.copy(ROOT / f"evals/baselines/{suite}.json", reports / f"{suite}-baseline.json")
    for suite, version in (("classify", "v1"), ("classify", "v2"), ("answer", "v2")):
        os.environ["EVALGATE_TOYS_URL"] = toys_url
        os.environ["EVALGATE_TOY_VERSION"] = version
        try:
            loaded = load_suite(ROOT / f"evals/suites/{suite}.yaml", split="test")
            result = run_suite(loaded, RunOptions(split="test", home=reports.parent / "home", use_store=False))
        finally:
            os.environ.pop("EVALGATE_TOY_VERSION", None)
        write_report(result.report, reports / f"{suite}-{version}.json")


@pytest.fixture(scope="session")
def viewer_url(tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    external = os.environ.get("EVALGATE_VIEWER_URL")
    if external:
        yield external.rstrip("/")
        return
    from tests.toy_server import toy_server
    from tests.viewer_helpers import viewer

    reports = tmp_path_factory.mktemp("reports")
    with toy_server() as toys:
        _seed(reports, toys)
    with viewer(reports) as url:
        yield url


@pytest.fixture(scope="session")
def browser() -> Iterator[object]:
    from playwright.sync_api import sync_playwright

    kwargs: dict[str, object] = {}
    exe = os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE") or "/opt/pw-browsers/chromium"
    if Path(exe).exists():
        kwargs["executable_path"] = exe
    with sync_playwright() as p:
        b = p.chromium.launch(**kwargs)
        yield b
        b.close()
