# ADR-0007: A stdlib viewer server instead of FastAPI in the wheel

- Status: Accepted
- Date: 2026-10-16

## Context

`evalgate serve <reports-dir>` is a read-only report viewer (FR-8): a runs list, a run detail page with filters, a comparison page, a small JSON API, static files and a health check. It ships inside the library wheel, which has hard budgets: wheel < 1 MB (NFR-7) and `import evalgate` < 300 ms (NFR-6). Every runtime dependency must also pass the license allowlist, and the default install should stay small. The viewer binds `127.0.0.1` by default and serves one engineer or one CI artifact at a time.

## Decision

Build the viewer on the standard library's `http.server.ThreadingHTTPServer` with Jinja2 templates, in [src/evalgate/viewer/server.py](../../src/evalgate/viewer/server.py) (475 lines, `wc -l`), with templates in [src/evalgate/viewer/templates/](../../src/evalgate/viewer/templates/) and static assets in [src/evalgate/viewer/static/](../../src/evalgate/viewer/static/). Jinja2 is already a dependency for the HTML report.

The server implements its own guards: autoescaped templates and a strict Content-Security-Policy, an optional bearer token (`EVALGATE_SERVE_TOKEN`), run IDs matched against a fixed pattern, reads confined to the reports directory, 50 requests per second per client (429), reports over 50 MB refused (413 in the error panel), and a `Host` header check against DNS rebinding (421).

FastAPI stays where it fits: the toy targets in `examples/toy-targets/`, which never ship in the wheel.

## Alternatives considered

- **FastAPI (with Starlette and an ASGI server such as Uvicorn) in the wheel (rejected).** It gives routing, validation, OpenAPI and middleware for free. It was rejected because it would add a web framework and a server to the runtime dependencies of a library whose server is one optional, local, read-only command. Those packages would count against the license check and the install footprint for every user, including CI jobs that never start the viewer. Their size and import cost were not measured for this decision; the stdlib server's own numbers below are within budget with room to spare.
- **FastAPI as an optional extra (rejected).** It would keep the core install small but make `evalgate serve` fail on a default install, and it would mean two code paths or a viewer that only some users have.

## Consequences

### Positive

- No web framework in the dependency set: runtime dependencies stay at pydantic, typer, pyyaml, httpx, numpy, duckdb, jinja2 and jsonschema ([pyproject.toml](../../pyproject.toml)).
- Budgets are met: wheel 0.1099 MB (NFR-7), `import evalgate` 3.7428 ms (NFR-6), run detail p95 8.1092 ms for 200 cases against a 200 ms budget (NFR-8) (`evals/reports/bench.json`, `make bench`).
- Every security control is in one file and covered by the viewer tests.

### Negative

- Routing, query parsing, rate limiting, security headers and error pages are hand-written and must be maintained and reviewed as security-sensitive code.
- `ThreadingHTTPServer` has no TLS, HTTP/2 or production hardening; the viewer is for local or trusted-network use and is not meant to be exposed publicly.
- The viewer has no generated OpenAPI document; its routes are listed in the module docstring and in the build spec §4.4.
