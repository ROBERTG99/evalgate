# syntax=docker/dockerfile:1
# Toy targets (FastAPI) used by the demo, the viewer seed and the meta-eval. Multi-stage: python:3.13-slim
# builder, distroless Python 3.13 runtime, non-root uid 10001, no apt-get. Data is synthetic.
FROM python:3.14-slim AS builder
ARG HTTPS_PROXY
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_CACHE_DIR=1 UV_LINK_MODE=copy
RUN pip install "uv==0.11.32"
WORKDIR /src
COPY pyproject.toml uv.lock README.md LICENSE ./
COPY examples/toy-targets ./examples/toy-targets
RUN uv export --frozen --no-dev --no-emit-workspace --no-hashes --package toy-targets -o /tmp/requirements.txt \
  && uv build --package toy-targets --wheel --out-dir /tmp/dist \
  && uv pip install --python /usr/local/bin/python3.13 --target /opt/app --no-deps -r /tmp/requirements.txt \
  && uv pip install --python /usr/local/bin/python3.13 --target /opt/app --no-deps /tmp/dist/*.whl \
  && find /opt/app -depth \( -name tests -o -name __pycache__ -o -name '*.pyi' \) -exec rm -rf {} + \
  && rm -rf /opt/app/bin
COPY evals/datasets/toys/faq_corpus.v1.jsonl /opt/data/toys/faq_corpus.v1.jsonl
COPY evals/datasets/meta/variants.v1.jsonl /opt/data/meta/variants.v1.jsonl

FROM gcr.io/distroless/python3-debian13:nonroot AS runtime
LABEL org.opencontainers.image.source="https://github.com/ROBERTG99/evalgate" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.title="evalgate-toy-targets"
ENV PYTHONPATH=/opt/app PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 TOY_DATA_DIR=/opt/data
COPY --from=builder /opt/app /opt/app
COPY --from=builder /opt/data /opt/data
USER 10001:10001
EXPOSE 8110
HEALTHCHECK --interval=5s --timeout=3s --start-period=5s --retries=10 \
  CMD ["python3", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8110/healthz', timeout=2).status == 200 else 1)"]
ENTRYPOINT ["python3", "-m", "toy_targets", "--host", "0.0.0.0", "--port", "8110"]
