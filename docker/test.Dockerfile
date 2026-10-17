# syntax=docker/dockerfile:1
# Test runner image for `make test-docker`: the repository with all dev dependencies and extras.
FROM python:3.14-slim
ARG HTTPS_PROXY
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_CACHE_DIR=1 UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH=/opt/venv/bin:$PATH PYTHONDONTWRITEBYTECODE=1 DEEPEVAL_TELEMETRY_OPT_OUT=YES
RUN pip install "uv==0.11.32" && useradd --uid 10001 --create-home tester
WORKDIR /src
COPY pyproject.toml uv.lock README.md LICENSE ./
COPY examples/toy-targets/pyproject.toml examples/toy-targets/pyproject.toml
COPY examples/toy-targets/src examples/toy-targets/src
RUN mkdir -p src/evalgate && touch src/evalgate/__init__.py \
  && uv sync --frozen --all-extras --no-install-project \
  && chown -R 10001:10001 /opt/venv
COPY --chown=10001:10001 . .
RUN uv sync --frozen --all-extras && chown -R 10001:10001 /src /opt/venv
USER 10001
CMD ["pytest", "tests/unit", "tests/integration", "tests/contract", "tests/harness", "-q"]
