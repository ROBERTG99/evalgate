import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def load(name: str) -> dict:
    return yaml.safe_load((ROOT / name).read_text())


def host_ports(service: dict) -> list[tuple[str, int]]:
    out = []
    for p in service.get("ports", []):
        m = re.fullmatch(r"(?P<ip>[\d.]+):(?P<host>\d+):\d+", str(p))
        assert m, f"port {p} must be ip:host:container"
        out.append((m["ip"], int(m["host"])))
    return out


def test_ports_in_range_and_healthchecks() -> None:
    compose = load("compose.yaml")
    services = compose["services"]
    for name, service in services.items():
        for ip, port in host_ports(service):
            assert ip == "127.0.0.1", name
            assert 8100 <= port <= 8199, (name, port)
    expected = {
        "toy-targets": 8110,
        "report-viewer": 8100,
        "otel-collector": 8180,
        "grafana": 8190,
        "prometheus": 8191,
        "jaeger": 8192,
        "langfuse-web": 8193,
        "langfuse-postgres": 8120,
        "langfuse-redis": 8130,
        "langfuse-clickhouse": 8140,
        "langfuse-minio": 8141,
    }
    for name, port in expected.items():
        assert port in [p for _, p in host_ports(services[name])], name
    for name in ("toy-targets", "report-viewer"):
        assert "profiles" not in services[name]
        assert services[name]["healthcheck"]["test"][0] == "CMD"
    assert services["report-viewer"]["depends_on"]["toy-targets"]["condition"] == "service_healthy"
    assert services["seed"]["profiles"] == ["tools"]
    assert services["langfuse-postgres"]["image"] == "pgvector/pgvector:pg16"
    for name in ("otel-collector", "prometheus", "grafana", "jaeger"):
        assert services[name]["profiles"] == ["observability"]


def test_dockerfiles_follow_the_rules() -> None:
    for name in ("evalgate", "toy-targets"):
        text = (ROOT / f"docker/{name}.Dockerfile").read_text()
        assert not [line for line in text.splitlines() if "apt-get" in line and not line.lstrip().startswith("#")]
        assert "ARG HTTPS_PROXY" in text
        assert "USER 10001" in text
        assert "HEALTHCHECK" in text
        assert "FROM python:3.13-slim AS builder" in text


def test_env_example_documents_variables() -> None:
    env = (ROOT / ".env.example").read_text()
    names = set(re.findall(r"^([A-Z_][A-Z0-9_]*)=", env, re.M))
    for shared in [
        "DEMO_MODE",
        "LIVE_EVAL_BUDGET_USD",
        "ANTHROPIC_API_KEY",
        "OPENAI_API_KEY",
        "AWS_REGION",
        "LANGFUSE_HOST",
        "LANGFUSE_PUBLIC_KEY",
        "LANGFUSE_SECRET_KEY",
        "OTEL_EXPORTER_OTLP_ENDPOINT",
        "LOG_LEVEL",
    ]:
        assert shared in names, shared
    used: set[str] = set()
    for path in [
        *(ROOT / "src").rglob("*.py"),
        *(ROOT / "scripts").glob("*.py"),
    ]:
        used |= set(re.findall(r"\bEVALGATE_[A-Z0-9_]+\b", path.read_text()))
    used -= {"EVALGATE_GUARD_ROOT", "EVALGATE_STOP_CHECK_CMD", "EVALGATE_LANGFUSE_URL", "EVALGATE_GITHUB_URL"}
    assert sorted(used - names) == []


def test_test_compose_services() -> None:
    compose = load("compose.test.yaml")
    services = compose["services"]
    assert {"tests", "e2e", "wiremock-langfuse", "wiremock-github", "promtool"} <= set(services)
    assert compose["networks"]["default"] == {"name": "evalgate_default", "external": True}
    ports = {name: [p for _, p in host_ports(s)] for name, s in services.items()}
    assert ports["wiremock-langfuse"] == [8142] and ports["wiremock-github"] == [8143]
    for name in ("wiremock-langfuse", "wiremock-github"):
        assert services[name]["image"].startswith("wiremock/wiremock:")
        assert services["tests"]["depends_on"][name]["condition"] == "service_healthy"
    command = " ".join(services["tests"]["command"])
    for suite in ("tests/unit", "tests/integration", "tests/contract", "tests/harness"):
        assert suite in command
    assert "promtool" in services["promtool"]["entrypoint"]
    assert services["e2e"]["environment"]["EVALGATE_VIEWER_URL"] == "http://report-viewer:8100"
    for name in ("test", "e2e"):
        text = (ROOT / f"docker/{name}.Dockerfile").read_text()
        assert "ARG HTTPS_PROXY" in text
        assert "USER " in text and "USER root" not in text
    assert "playwright==1.56.0" in (ROOT / "docker/e2e.Dockerfile").read_text()
