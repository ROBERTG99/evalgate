import json
from pathlib import Path

from evalgate.export.langfuse import LangfuseExporter
from tests.contract.wiremock_double import received, wiremock
from tests.factories import make_report

HERE = Path(__file__).parent


def ten_case_report():  # type: ignore[no-untyped-def]
    scores = {"accuracy": [1.0, 0.0] * 5, "format": [1.0] * 10, "tools": [0.5] * 10}
    return make_report(scores, suite="classify", ids=[f"cls-{i:03d}" for i in range(10)])


def test_10_traces_30_scores() -> None:
    with wiremock("langfuse") as url:
        outcome = LangfuseExporter(url, "pk-lf-test", "sk-lf-test", backoff_s=0).export(ten_case_report())
        assert outcome.ok, outcome.error
        requests = received(url)
    assert (outcome.traces, outcome.scores) == (10, 30)
    events = [e for r in requests for e in json.loads(r["body"])["batch"]]
    assert sum(e["type"] == "trace-create" for e in events) == 10
    assert sum(e["type"] == "score-create" for e in events) == 30
    expected = json.loads((HERE / "expected_requests.json").read_text())
    assert [r["url"] for r in requests] == expected["urls"]
    assert [r["method"] for r in requests] == expected["methods"]
    actual = sorted((e["type"], e["id"], json.dumps(e["body"], sort_keys=True)) for e in events)
    assert actual == sorted((e["type"], e["id"], json.dumps(e["body"], sort_keys=True)) for e in expected["events"])


def test_bad_credentials_fail_without_retry_storm() -> None:
    with wiremock("langfuse") as url:
        outcome = LangfuseExporter(url, "pk-wrong", "sk-wrong", backoff_s=0).export(ten_case_report())
        assert not outcome.ok
        assert "401" in (outcome.error or "")
        assert len(received(url)) == 1


def test_langfuse_down_retries_then_fails() -> None:
    outcome = LangfuseExporter("http://127.0.0.1:9", "pk", "sk", backoff_s=0).export(ten_case_report())
    assert not outcome.ok
    assert "after 3 attempts" in (outcome.error or "")


def test_non_json_success_is_a_failed_export_not_a_crash() -> None:
    import httpx

    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, text="<html>proxy</html>")))
    outcome = LangfuseExporter("http://langfuse.local", "pk", "sk", client=client, backoff_s=0).export(
        ten_case_report()
    )
    assert not outcome.ok and "without JSON" in (outcome.error or "")
