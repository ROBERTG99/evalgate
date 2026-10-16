"""Playwright + axe against the viewer; writes the screenshots in docs/images/ (T-30)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
import pytest

pytestmark = pytest.mark.e2e
ROOT = Path(__file__).resolve().parents[2]
IMAGES = ROOT / "docs" / "images"


def runs(url: str) -> list[dict[str, Any]]:
    return httpx.get(f"{url}/api/runs", timeout=10).json()["runs"]


def pick(url: str, suite: str, passed: bool) -> str:
    return next(r["run_id"] for r in runs(url) if r["suite"] == suite and r["passed"] is passed)


def compare_url(url: str) -> str:
    base = next(r["run_id"] for r in runs(url) if r["suite"] == "classify" and r["passed"])
    cand = pick(url, "classify", False)
    return f"{url}/compare?base={base}&cand={cand}"


def wait_compare(page: Any) -> None:
    page.wait_for_selector('main[aria-busy="false"]', timeout=20_000)


def serious(page: Any) -> list[str]:
    from axe_playwright_python.sync_playwright import Axe

    results = Axe().run(page)
    return [
        f"{v['id']}: {v['help']}" for v in results.response["violations"] if v.get("impact") in ("serious", "critical")
    ]


def test_no_serious_axe_violations(viewer_url: str, browser: Any) -> None:
    targets = [
        f"{viewer_url}/",
        f"{viewer_url}/runs/{pick(viewer_url, 'classify', False)}",
        f"{viewer_url}/runs/{pick(viewer_url, 'classify', False)}?status=failed",
        f"{viewer_url}/runs/{pick(viewer_url, 'answer', True)}",
        compare_url(viewer_url),
        f"{viewer_url}/compare",
        f"{viewer_url}/runs/00000000-0000-0000-0000-000000000000",
    ]
    problems = {}
    for scheme in ("light", "dark"):
        context = browser.new_context(color_scheme=scheme)
        page = context.new_page()
        for target in targets:
            page.goto(target)
            if "/compare?" in target:
                wait_compare(page)
            found = serious(page)
            if found:
                problems[f"{scheme} {target}"] = found
        context.close()
    assert problems == {}


def test_mobile_375_no_page_overflow(viewer_url: str, browser: Any) -> None:
    context = browser.new_context(viewport={"width": 375, "height": 812}, device_scale_factor=2)
    page = context.new_page()
    page.goto(f"{viewer_url}/runs/{pick(viewer_url, 'classify', False)}")
    assert page.evaluate("document.documentElement.scrollWidth") <= 375
    IMAGES.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(IMAGES / "mobile-375.png"), full_page=False)
    context.close()


def test_keyboard_focus_visible(viewer_url: str, browser: Any) -> None:
    page = browser.new_page()
    page.goto(f"{viewer_url}/")
    page.keyboard.press("Tab")
    outline = page.evaluate("getComputedStyle(document.activeElement).outlineStyle")
    assert outline != "none"
    page.close()


def test_theme_toggle_and_filters_without_js(viewer_url: str, browser: Any) -> None:
    context = browser.new_context(java_script_enabled=False)
    page = context.new_page()
    run = pick(viewer_url, "classify", False)
    page.goto(f"{viewer_url}/runs/{run}")
    page.select_option("select[name=status]", "failed")
    page.click("form.filters button[type=submit]")
    assert "status=failed" in page.url
    context.close()
    page = browser.new_page()
    page.goto(f"{viewer_url}/")
    page.click("[data-theme-toggle]")
    assert page.evaluate("document.documentElement.getAttribute('data-theme')") in ("dark", "light")
    page.close()


def test_screenshots(viewer_url: str, browser: Any) -> None:
    IMAGES.mkdir(parents=True, exist_ok=True)
    context = browser.new_context(
        viewport={"width": 1280, "height": 900},
        color_scheme="light",
        record_video_dir=str(IMAGES / ".video"),
        record_video_size={"width": 1280, "height": 900},
    )
    page = context.new_page()
    page.goto(f"{viewer_url}/")
    page.screenshot(path=str(IMAGES / "runs-list.png"), full_page=True)
    page.goto(compare_url(viewer_url))
    wait_compare(page)
    page.screenshot(path=str(IMAGES / "compare-regression.png"), full_page=True)
    page.goto(f"{viewer_url}/runs/{pick(viewer_url, 'classify', False)}?status=failed")
    page.wait_for_timeout(500)
    video = page.video
    context.close()
    if video is not None:
        video.save_as(str(IMAGES / "demo.webm"))
        for leftover in (IMAGES / ".video").glob("*"):
            leftover.unlink()
        (IMAGES / ".video").rmdir()
    dark = browser.new_context(viewport={"width": 1280, "height": 900}, color_scheme="dark")
    page = dark.new_page()
    page.goto(f"{viewer_url}/runs/{pick(viewer_url, 'answer', True)}")
    page.screenshot(path=str(IMAGES / "run-detail-dark.png"), full_page=False)
    dark.close()
    for name in ("runs-list", "run-detail-dark", "compare-regression", "mobile-375"):
        assert (IMAGES / f"{name}.png").stat().st_size > 10_000, name
