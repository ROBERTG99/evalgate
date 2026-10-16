import json
import sys
from pathlib import Path

import httpx

from evalgate.report.markdown import render_markdown
from evalgate.stats.gate import check
from tests.contract.wiremock_double import received, wiremock
from tests.factories import make_report

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from pr_comment import MARKER, CommentClient  # noqa: E402


def regressed_markdown() -> str:
    base = make_report({"label_accuracy": [1.0] * 60}, suite="classify", threshold=0.9)
    cand = make_report({"label_accuracy": [0.0] * 10 + [1.0] * 50}, suite="classify", threshold=0.9)
    result = check(cand, report_sha256="c" * 64, baseline=base)
    assert not result.passed
    return render_markdown(cand, result, baseline=base)


def test_upsert_single_comment() -> None:
    body = regressed_markdown()
    with wiremock("github") as url:
        client = CommentClient(url, "test-token", httpx.Client())
        first = client.upsert("acme/widgets", 7, "classify", body)
        second = client.upsert("acme/widgets", 7, "classify", body)
        requests = received(url)
    assert (first.action, second.action) == ("created", "updated")
    assert second.comment_id == 4242
    writes = [r for r in requests if r["method"] in ("POST", "PATCH")]
    assert [r["method"] for r in writes] == ["POST", "PATCH"]  # exactly one comment, edited in place
    assert all("/comments/13" not in r["url"] for r in writes)  # a human comment with pasted markers is ignored
    for r in writes:
        sent = json.loads(r["body"])["body"]
        assert sent.startswith(MARKER)
        assert "<!-- evalgate:suite=classify -->" in sent
        assert "regression" in sent and "-16.67 pp" in sent


def test_403_skips(tmp_path: Path, monkeypatch, capsys) -> None:  # type: ignore[no-untyped-def]
    import pr_comment

    with wiremock("github") as url:
        outcome = CommentClient(url, "test-token", httpx.Client()).upsert("acme/forked", 9, "classify", "body")
        assert outcome.action == "skipped"
        assert "403" in (outcome.reason or "")
        body = tmp_path / "r.md"
        body.write_text("report")
        monkeypatch.setenv("GITHUB_API_URL", url)
        code = pr_comment.main(["--repo", "acme/forked", "--pr", "9", "--suite", "classify", "--body-file", str(body)])
    assert code == 0  # the gate is unchanged
    assert "::warning" in capsys.readouterr().out


def test_other_suites_do_not_collide() -> None:
    with wiremock("github") as url:
        client = CommentClient(url, "t", httpx.Client())
        client.upsert("acme/widgets", 7, "classify", "x")
        other = client.upsert("acme/widgets", 7, "answer", "y")
    assert other.action == "created"
