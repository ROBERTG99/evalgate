from pathlib import Path

import httpx

from tests.integration.viewer.test_pages import RUN_A, write
from tests.viewer_helpers import viewer


def test_rate_limit_and_token(tmp_path: Path) -> None:
    write(tmp_path / "a.json", RUN_A, [1.0] * 3)
    with viewer(tmp_path, token="s3cret") as url:
        assert httpx.get(url + "/").status_code == 401
        assert httpx.get(url + "/", headers={"Authorization": "Bearer wrong"}).status_code == 401
        assert httpx.get(url + "/healthz").status_code == 200  # healthchecks need no token
        auth = {"Authorization": "Bearer s3cret"}
        assert httpx.get(url + "/", headers=auth).status_code == 200
    with viewer(tmp_path) as url, httpx.Client() as client:
        codes = [client.get(url + "/api/runs").status_code for _ in range(60)]
    assert 429 in codes
    assert codes[0] == 200


def test_read_only_and_no_path_traversal(tmp_path: Path) -> None:
    (tmp_path / "reports").mkdir()
    write(tmp_path / "reports" / "a.json", RUN_A, [1.0] * 3)
    (tmp_path / "secret.json").write_text('{"schema": "evalgate.report.v1"}')
    with viewer(tmp_path / "reports") as url:
        assert httpx.post(url + "/").status_code == 405
        for path in ["/static/..%2F..%2Fsecret.json", "/runs/..%2Fsecret", "/static/%2e%2e/server.py"]:
            assert httpx.get(url + path).status_code in (400, 404), path
        errors = httpx.get(url + "/api/runs").json()["errors"]
    assert errors == []  # files outside the reports directory are never read


def test_binds_loopback_by_default() -> None:
    import inspect

    from evalgate.viewer import server

    assert inspect.signature(server.serve).parameters["host"].default == "127.0.0.1"


def test_foreign_host_rejected(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    write(tmp_path / "a.json", RUN_A, [1.0] * 3)
    with viewer(tmp_path) as url:
        assert httpx.get(url + "/", headers={"Host": "evil.example"}).status_code == 421
        assert httpx.get(url + "/healthz", headers={"Host": "attacker.test:8100"}).status_code == 421
        assert httpx.get(url + "/", headers={"Host": "localhost:8100"}).status_code == 200
        assert httpx.get(url + "/", headers={"Host": "[::1]:8100"}).status_code == 200
    monkeypatch.setenv("EVALGATE_SERVE_ALLOWED_HOSTS", "report-viewer")
    with viewer(tmp_path) as url:
        assert httpx.get(url + "/", headers={"Host": "report-viewer:8100"}).status_code == 200
