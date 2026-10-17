# syntax=docker/dockerfile:1
# E2E runner: the official Playwright image (browsers preinstalled), the test dependencies, and evalgate itself
# (the HTML report axe test renders a report) with its dependencies from uv.lock.
FROM mcr.microsoft.com/playwright/python:v1.56.0-noble
ARG HTTPS_PROXY
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_CACHE_DIR=1 PYTHONDONTWRITEBYTECODE=1
RUN pip install --break-system-packages "uv==0.11.32" "playwright==1.56.0" "pytest==8.4.2" "httpx==0.28.1" \
    "axe-playwright-python==0.1.8" "pyyaml==6.0.3"
WORKDIR /opt/evalgate
COPY pyproject.toml uv.lock README.md LICENSE ./
COPY examples/toy-targets/pyproject.toml examples/toy-targets/pyproject.toml
COPY src src
COPY prompts prompts
RUN uv export --frozen --package evalgate --no-dev --no-emit-workspace --quiet -o /tmp/requirements.txt \
  && pip install --break-system-packages --require-hashes -r /tmp/requirements.txt \
  && pip install --break-system-packages --no-deps . \
  && rm -f /tmp/requirements.txt
WORKDIR /src
USER 1001:1001
CMD ["python", "-m", "pytest", "-o", "addopts=", "-p", "no:cacheprovider", "-o", "markers=e2e: browser tests", "tests/e2e", "-m", "e2e", "-q"]
