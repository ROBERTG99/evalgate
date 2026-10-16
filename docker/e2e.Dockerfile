# syntax=docker/dockerfile:1
# E2E runner: the official Playwright image (browsers preinstalled) plus the test dependencies.
FROM mcr.microsoft.com/playwright/python:v1.56.0-noble
ARG HTTPS_PROXY
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_CACHE_DIR=1 PYTHONDONTWRITEBYTECODE=1
RUN pip install --break-system-packages "playwright==1.56.0" "pytest==8.4.2" "httpx==0.28.1" "axe-playwright-python==0.1.8" "pyyaml==6.0.3"
WORKDIR /src
USER 1001:1001
CMD ["python", "-m", "pytest", "-o", "addopts=", "-p", "no:cacheprovider", "-o", "markers=e2e: browser tests", "tests/e2e", "-m", "e2e", "-q"]
