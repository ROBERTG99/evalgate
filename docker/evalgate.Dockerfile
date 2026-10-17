# syntax=docker/dockerfile:1
# evalgate CLI and report viewer. Multi-stage: python:3.13-slim builder, distroless Python 3.13 runtime
# (no shell, no package manager), non-root uid 10001, no apt-get. See docs/DECISIONS.md for the size budget.
FROM python:3.13-slim AS builder
ARG HTTPS_PROXY
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_CACHE_DIR=1 UV_LINK_MODE=copy
RUN pip install "uv==0.11.32"
WORKDIR /src
COPY pyproject.toml uv.lock README.md LICENSE ./
COPY examples/toy-targets/pyproject.toml examples/toy-targets/pyproject.toml
COPY src ./src
COPY prompts ./prompts
RUN uv export --frozen --no-dev --no-emit-workspace --no-hashes --package evalgate -o /tmp/requirements.txt \
  && uv build --package evalgate --wheel --out-dir /tmp/dist \
  && uv pip install --python /usr/local/bin/python3.13 --target /opt/app --no-deps -r /tmp/requirements.txt \
  && uv pip install --python /usr/local/bin/python3.13 --target /opt/app --no-deps /tmp/dist/*.whl \
  && find /opt/app -depth \( -name tests -o -name __pycache__ -o -name '*.pyi' \) -exec rm -rf {} + \
  && rm -rf /opt/app/bin /opt/app/numpy/_core/include \
  && mkdir -p /out/reports /out/data

FROM gcr.io/distroless/python3-debian13:nonroot AS runtime
LABEL org.opencontainers.image.source="https://github.com/ROBERTG99/evalgate" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.title="evalgate"
ENV PYTHONPATH=/opt/app PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 EVALGATE_HOME=/data/.evalgate
COPY --from=builder /opt/app /opt/app
COPY --from=builder --chown=10001:10001 /out/reports /reports
COPY --from=builder --chown=10001:10001 /out/data /data
USER 10001:10001
WORKDIR /data
EXPOSE 8100
HEALTHCHECK --interval=5s --timeout=3s --start-period=5s --retries=10 \
  CMD ["python3", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8100/healthz', timeout=2).status == 200 else 1)"]
ENTRYPOINT ["python3", "-m", "evalgate.cli"]
CMD ["serve", "/reports", "--host", "0.0.0.0", "--port", "8100"]
