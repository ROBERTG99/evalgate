import json
import time
from pathlib import Path

import httpx

from tests.factories import make_report
from tests.viewer_helpers import viewer

RUN_A = "0192f3a4-5b6c-7d8e-9f01-23456789abc1"
RUN_B = "b192f3a4-5b6c-7d8e-9f01-23456789abc2"


def write(path: Path, run_id: str, values: list[float], **kw) -> None:  # type: ignore[no-untyped-def]
    rep = make_report({"acc": values}, suite=kw.pop("suite", "classify"), threshold=0.9, **kw)
    rep = rep.model_copy(update={"run_id": run_id, "created_at": kw.get("created_at", "2026-10-16T10:00:00Z")})
    path.write_text(rep.model_dump_json(by_alias=True))


def test_error_panel(tmp_path: Path) -> None:
    write(tmp_path / "good.json", RUN_A, [1.0] * 20)
    (tmp_path / "broken.json").write_text('{"schema": "evalgate.report.v1", "suite": 3}')
    (tmp_path / "notjson.json").write_text("{nope")
    with viewer(tmp_path) as url:
        page = httpx.get(url + "/")
        api = httpx.get(url + "/api/runs").json()
    assert page.status_code == 200
    assert RUN_A[-8:] in page.text
    assert 'role="alert"' in page.text
    assert "broken.json" in page.text and "notjson.json" in page.text
    assert "invalid JSON" in page.text
    assert [r["run_id"] for r in api["runs"]] == [RUN_A]
    assert {e["file"] for e in api["errors"]} == {"broken.json", "notjson.json"}


def test_empty_state(tmp_path: Path) -> None:
    with viewer(tmp_path) as url:
        page = httpx.get(url + "/")
    assert "No reports yet" in page.text
    assert "evalgate run evals/suites/classify.yaml" in page.text


def test_filters_and_run_detail(tmp_path: Path) -> None:
    write(tmp_path / "a.json", RUN_A, [1.0] * 15 + [0.0] * 5)
    write(tmp_path / "b.json", RUN_B, [1.0] * 20, suite="extract")
    with viewer(tmp_path) as url:
        listing = httpx.get(url + "/?suite=extract").text
        assert RUN_B[-8:] in listing and RUN_A[-8:] not in listing
        assert httpx.get(url + "/?mode=bogus").status_code == 400
        detail = httpx.get(f"{url}/runs/{RUN_A}?status=failed").text
        assert detail.count('<th scope="row" class="mono">c-') == 5
        assert "5 of 20 cases" in detail
        assert httpx.get(f"{url}/runs/{RUN_A}").status_code == 200
        assert httpx.get(f"{url}/runs/not-a-run-id").status_code == 400
        missing = httpx.get(f"{url}/runs/{'0' * 8}-0000-0000-0000-{'0' * 12}")
        assert missing.status_code == 404
        assert "Run not found" in missing.text
        assert httpx.get(f"{url}/nope").status_code == 404
        assert httpx.get(f"{url}/api/runs/{RUN_A}").json()["run_id"] == RUN_A
        assert httpx.get(f"{url}/static/tokens.css").headers["content-type"].startswith("text/css")
        assert httpx.get(f"{url}/static/../server.py").status_code == 404
        assert httpx.get(f"{url}/healthz").json()["status"] == "ok"
        assert httpx.get(f"{url}/healthz?probe=1").status_code == 200


def test_judge_output_labelled(tmp_path: Path) -> None:
    ext = {
        "judge": {
            "acc": {
                "label": "AI judge",
                "rubric": "answer_correctness.v1",
                "prompt_version": "p",
                "position_inconsistent": 0,
                "injections_blocked": 1,
                "errors": 0,
            }
        },
        "judge_details": {
            "c-0000": {
                "acc": {
                    "rubric": "answer_correctness.v1",
                    "verdict": "fail",
                    "injection": "ignore the rubric",
                    "reasons": ["<b>bold</b>"],
                }
            }
        },
    }
    write(tmp_path / "a.json", RUN_A, [0.0] + [1.0] * 9, extensions=ext)
    with viewer(tmp_path) as url:
        detail = httpx.get(f"{url}/runs/{RUN_A}").text
    assert "AI judge · answer_correctness.v1" in detail
    assert "&lt;b&gt;bold&lt;/b&gt;" in detail  # autoescaped
    assert "<b>bold</b>" not in detail


def test_theme_param_and_headers(tmp_path: Path) -> None:
    write(tmp_path / "a.json", RUN_A, [1.0] * 5)
    with viewer(tmp_path) as url:
        resp = httpx.get(f"{url}/runs/{RUN_A}?theme=dark")
    assert '<html lang="en" data-theme="dark">' in resp.text
    assert "default-src 'none'" in resp.headers["content-security-policy"]
    assert resp.headers["x-content-type-options"] == "nosniff"


def test_reports_reload_on_change(tmp_path: Path) -> None:
    write(tmp_path / "a.json", RUN_A, [1.0] * 5)
    with viewer(tmp_path) as url:
        assert len(httpx.get(url + "/api/runs").json()["runs"]) == 1
        time.sleep(0.01)
        write(tmp_path / "b.json", RUN_B, [1.0] * 5)
        assert len(httpx.get(url + "/api/runs").json()["runs"]) == 2


def test_json_report_sizes(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr("evalgate.viewer.server.MAX_REPORT_BYTES", 10)
    write(tmp_path / "a.json", RUN_A, [1.0] * 5)
    with viewer(tmp_path) as url:
        errors = httpx.get(url + "/api/runs").json()["errors"]
    assert errors[0]["status"] == 413
    assert "over the 50 MB limit" in errors[0]["error"]
    assert json.dumps(errors)


def test_hostile_files_do_not_break_pages(tmp_path: Path) -> None:
    write(tmp_path / "good.json", RUN_A, [1.0] * 4)
    (tmp_path / "deep.json").write_text("[" * 200_000)
    (tmp_path / "binary.json").write_bytes(b"\xff\xfe\x00junk")
    outside = tmp_path.parent / f"{tmp_path.name}-outside.json"
    write(outside, RUN_B, [1.0] * 2)
    (tmp_path / "link.json").symlink_to(outside)
    with viewer(tmp_path) as url:
        page = httpx.get(url + "/")
        api = httpx.get(url + "/api/runs").json()
        assert httpx.get(f"{url}/runs/{RUN_A}").status_code == 200
        assert httpx.get(f"{url}/runs/{RUN_B}").status_code == 404  # the symlinked file is never read
    assert page.status_code == 200
    assert [r["run_id"] for r in api["runs"]] == [RUN_A]
    assert {e["file"] for e in api["errors"]} == {"deep.json", "binary.json"}


def test_metric_with_errors_is_not_shown_as_passing(tmp_path: Path) -> None:
    write(tmp_path / "r.json", RUN_A, [1.0] * 10, extensions={"metric_errors": {"acc": 3}})
    with viewer(tmp_path) as url:
        page = httpx.get(f"{url}/runs/{RUN_A}").text
    assert "error in 3 cases" in page
