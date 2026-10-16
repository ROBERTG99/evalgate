import time
from pathlib import Path

import httpx

from tests.integration.viewer.test_pages import RUN_A, RUN_B, write
from tests.viewer_helpers import viewer


def test_loading_then_result(tmp_path: Path) -> None:
    write(tmp_path / "base.json", RUN_A, [1.0] * 200)
    write(tmp_path / "cand.json", RUN_B, [0.0] * 20 + [1.0] * 180)
    with viewer(tmp_path) as url:
        first = httpx.get(f"{url}/compare?base={RUN_A}&cand={RUN_B}")
        assert first.status_code == 200
        assert 'aria-busy="true"' in first.text
        # WCAG 2.2.1: no meta refresh; app.js reloads every second, and a link refreshes without JavaScript
        assert 'http-equiv="refresh"' not in first.text
        assert (
            f'<a href="/compare?base={RUN_A}&amp;cand={RUN_B}" data-auto-refresh="1000">Refresh now</a>' in first.text
        )
        deadline = time.monotonic() + 10
        while True:
            page = httpx.get(f"{url}/compare?base={RUN_A}&cand={RUN_B}")
            if 'aria-busy="false"' in page.text or time.monotonic() > deadline:
                break
            time.sleep(0.2)
    assert 'aria-busy="false"' in page.text
    assert "-10.00" in page.text  # 20 of 200 cases regressed
    assert "regression" in page.text
    assert page.text.index("c-0000") < page.text.index("Cases that moved") + 5000
    assert "▼" in page.text


def test_compare_pick_and_errors(tmp_path: Path) -> None:
    write(tmp_path / "base.json", RUN_A, [1.0] * 10)
    with viewer(tmp_path) as url:
        assert "Baseline" in httpx.get(f"{url}/compare").text
        assert httpx.get(f"{url}/compare?base={RUN_A}&cand=x").status_code == 400
        assert httpx.get(f"{url}/compare?base={RUN_A}&cand={RUN_B}").status_code == 404
