# Decisions

Each entry: date, decision, alternatives, reason. Architectural decisions also have an ADR in `docs/adr/`.

| Date | Decision | Alternatives | Reason |
|---|---|---|---|
| 2026-10-16 | Toy targets are a uv workspace member (`examples/toy-targets`) used through the `dev` dependency group. | Separate repository; vendored module under `tests/`. | Keeps them out of the wheel while letting tests import them. |
| 2026-10-16 | Judge prompts live in `prompts/` and are force-included in the wheel as `evalgate/prompts/`. | Store prompts only inside the package. | The spec places prompts at the repository root; the installed library still needs them. |
| 2026-10-16 | Provider SDKs (`anthropic`, `openai`) are optional extras imported lazily by `evalgate.llm.gateway`. | Hard dependencies. | Keeps `import evalgate` under 300 ms and the default install offline-only. |
| 2026-10-16 | The `[langfuse]` extra is empty: the exporter uses the Langfuse public ingestion HTTP API through `httpx`. | Depend on the Langfuse SDK. | The SDK (v3+) is OTel based and harder to point at a WireMock double; the HTTP API is the stable contract. |
| 2026-10-16 | Pinned tool versions are committed in `tools/versions.env` and copied to the gitignored `.tools/versions.env` on install. | Commit `.tools/versions.env` directly. | The spec gitignores `.tools/`; a committed source of truth is needed for reproducibility. |
| 2026-10-16 | Tool versions: hadolint 2.15.1, trivy 0.76.0, shellcheck 0.11.0, actionlint 1.7.12, gitleaks 8.30.1, markdownlint-cli2 0.23.3. | `latest` at install time. | GitHub API `latest` lookups are blocked in the cloud container; these are the newest versions whose release assets were downloadable on 2026-10-16. |
