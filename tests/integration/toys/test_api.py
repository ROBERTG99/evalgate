import json
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[3]


def rows(name: str, split: str = "dev") -> list[dict]:
    path = ROOT / f"evals/datasets/toys/{name}.v1.jsonl"
    return [r for r in map(json.loads, path.read_text().splitlines()) if r["split"] == split]


def accuracy(url: str, version: str) -> float:
    data = rows("classify")
    with httpx.Client(base_url=url, headers={"X-Toy-Version": version}) as client:
        hits = sum(client.post("/classify", json=r["input"]).json()["label"] == r["expected"]["label"] for r in data)
    return hits / len(data)


def test_v2_regresses(toys_url: str) -> None:
    v1, v2 = accuracy(toys_url, "v1"), accuracy(toys_url, "v2")
    assert v1 >= 0.90
    assert v2 < v1 - 0.05


@pytest.mark.parametrize("header", [{"X-Toy-Version": "v9"}, {"X-Toy-Variant": "var-99"}, {"X-Toy-Variant": "var-20"}])
def test_unknown_version_or_variant_400(toys_url: str, header: dict[str, str]) -> None:
    resp = httpx.post(f"{toys_url}/classify", json={"text": "hi"}, headers=header)  # var-20 is an extract variant
    assert resp.status_code == 400


def test_endpoints_shapes_and_steps(toys_url: str) -> None:
    doc = rows("extract")[0]
    ext = httpx.post(f"{toys_url}/extract", json=doc["input"]).json()
    assert {k: ext[k] for k in doc["expected"]} == doc["expected"]
    q = rows("answer")[0]
    ans = httpx.post(f"{toys_url}/answer", json=q["input"]).json()
    assert ans["citations"] == [q["expected"]["doc_id"]]
    assert [s["node"] for s in ans["steps"]] == ["search_faq", "read_doc", "generate"]
    assert ans["steps"][-1]["model"] == "toy-model"
    assert ans["steps"][-1]["input_tokens"] > 0


def test_health_metrics_openapi(toys_url: str) -> None:
    health = httpx.get(f"{toys_url}/healthz").json()
    assert health == {"status": "ok", "documents": 40, "variants": 50}
    httpx.post(f"{toys_url}/classify", json={"text": "my parcel never arrived"})
    metrics = httpx.get(f"{toys_url}/metrics").text
    assert 'toy_requests_total{endpoint="classify",version="v1",status="200"}' in metrics
    spec = httpx.get(f"{toys_url}/openapi.json").json()
    assert {"/classify", "/extract", "/answer", "/healthz", "/metrics"} <= set(spec["paths"])


def test_every_variant_answers(toys_url: str) -> None:
    variants = [json.loads(x) for x in (ROOT / "evals/datasets/meta/variants.v1.jsonl").read_text().splitlines()]
    samples = {
        "classify": {"text": "I was charged twice"},
        "extract": rows("extract")[0]["input"],
        "answer": rows("answer")[0]["input"],
    }
    for v in variants:
        if v["meta"]["mutation"] == "latency_ms" and v["meta"]["params"]["ms"] > 100:
            continue  # exercised by the meta-eval; keeps this test fast
        system = v["input"]["system"]
        resp = httpx.post(f"{toys_url}/{system}", json=samples[system], headers={"X-Toy-Variant": v["id"]})
        assert resp.status_code == 200, (v["id"], resp.text)


def test_error_responses_are_counted() -> None:
    """ToyTargetErrorRate must see validation errors, unknown paths and bad headers, not only handled 400s."""
    from fastapi.testclient import TestClient

    from toy_targets.app import create_app

    client = TestClient(create_app())
    assert client.post("/classify", json={"wrong": "field"}).status_code == 422
    assert client.post("/nope", json={}).status_code == 404
    assert client.post("/classify", json={"text": "x"}, headers={"X-Toy-Version": "v9"}).status_code == 400
    assert client.post("/classify", json={"text": "x"}).status_code == 200
    metrics = client.get("/metrics").text
    assert 'toy_requests_total{endpoint="classify",version="v1",status="422"} 1' in metrics
    assert 'toy_requests_total{endpoint="other",version="v1",status="404"} 1' in metrics
    assert 'toy_requests_total{endpoint="classify",version="invalid",status="400"} 1' in metrics
    assert 'toy_requests_total{endpoint="classify",version="v1",status="200"} 1' in metrics
    assert 'endpoint="metrics"' not in metrics and 'endpoint="healthz"' not in metrics
