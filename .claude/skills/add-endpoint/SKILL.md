---
name: add-endpoint
description: Add or change an HTTP route in the evalgate viewer (src/evalgate/viewer/server.py, stdlib server) or in the toy-targets FastAPI app (examples/toy-targets/src/toy_targets/app.py). Use for any new page, JSON API or toy endpoint. There are no TypeScript types to regenerate.
---

# Add an endpoint

Two HTTP surfaces exist: the viewer on port 8100 (stdlib `ThreadingHTTPServer` plus Jinja2, ships in the wheel) and the toy targets on port 8110 (FastAPI, never in the wheel). Contracts for both are in §4.4 of `docs/specs/000-build-spec.md` (or `BUILD.md`).

## Steps

1. Decide the surface and write the contract first: method, path, query or body, response shape, and error codes (viewer: 400, 404, 413 above 50 MB, 429 above 50 requests/s per client; toy targets: 400 for an unknown `X-Toy-Version` or `X-Toy-Variant`).
2. Write the failing tests:
   - Viewer: `tests/integration/viewer/test_pages.py` (or a new file) starting the server on a random loopback port with a reports directory in `tmp_path`; cover success, empty, error and 404, and the security cases in `tests/integration/viewer/test_security.py` (path traversal, run ID pattern `^[0-9a-f-]{36}$`, bearer token when `EVALGATE_SERVE_TOKEN` is set).
   - Toy targets: `tests/integration/toys/test_api.py` with FastAPI's `TestClient`; the Schemathesis contract in `tests/contract/test_toys_openapi.py` picks the route up from `/openapi.json`.
3. Run them and watch them fail: `uv run pytest tests/integration/viewer -x` or `uv run pytest tests/integration/toys -x`.
4. Implement:
   - Viewer: add the route to the dispatch in `src/evalgate/viewer/server.py`, render a template under `src/evalgate/viewer/templates/` with autoescape on, read only inside the reports directory, and implement all four states (loading, empty, error, success). JSON routes live under `/api/`.
   - Toy targets: add a Pydantic request and response model and the route in `examples/toy-targets/src/toy_targets/app.py`; responses include `steps` with synthetic token counts priced as `toy-model`.
5. For a toy-target route, regenerate the OpenAPI document with `uv run python scripts/export_openapi.py` (part of `make docs`) and commit it.
6. For a viewer page, run the `ux-reviewer` subagent and add the page to `tests/e2e/test_viewer.py` (axe check, screenshot in `docs/images/` if it is a §13 screen).
7. Run `make check-fast`, then `uv run pytest tests/integration tests/contract -q`.
8. Document the route in `docs/architecture.md` or `docs/contracts/`, and record evidence in `PROGRESS.md`.

## Done when

- The route answers its success and error codes in tests, and the viewer route renders all four states.
- `make check-fast` is green and, for a viewer page, `make e2e` reports no serious axe violation.
- The toy-targets OpenAPI document matches the app, and no TypeScript or frontend types are expected anywhere.
