---
paths:
  - "docker/**"
  - "compose*.yaml"
---

# Docker

- Multi-stage builds on `python:3.13-slim`, `ARG HTTPS_PROXY` in every stage that downloads, no `apt-get`.
- Run as non-root user 10001; `HEALTHCHECK` on `/healthz`.
- Host ports 8100-8199 bound to `127.0.0.1` only.
- Containers are offline at runtime; live model calls run from the host.
- Images: `evalgate` < 250 MB, `toy-targets` < 300 MB; hadolint and trivy must be clean.
