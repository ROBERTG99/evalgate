---
paths:
  - "src/evalgate/viewer/**"
  - "src/evalgate/targets/**"
  - "src/evalgate/llm/**"
  - "src/evalgate/suite/**"
  - "scripts/pr_comment.py"
  - "docs/security.md"
---

# Security

- Suites are trusted configuration (`python:` targets run code); YAML through `safe_load` only.
- HTTP targets must match `EVALGATE_HTTP_ALLOWED_HOSTS` (SSRF).
- Viewer: read-only, binds `127.0.0.1` by default, bearer token when `EVALGATE_SERVE_TOKEN` is set,
  run IDs matched against `^[0-9a-f-]{36}$`, reads confined to the reports directory, 50 req/s per client.
- PR comments escape Markdown and cut excerpts at 200 characters.
- Secrets only from the environment and never in reports or logs.
