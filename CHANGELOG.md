# Changelog

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses [Semantic Versioning](https://semver.org/). Contracts (`schemas/*.v1.json`) change only additively within a major version.

## [Unreleased]

## [0.1.0] - 2026-10-16

First release.

### Added

- `evalgate run`, `check`, `report`, `calibrate`, `serve`, `gc`, `schema`, `import` and `export` commands with exit codes 0 to 5.
- Contracts `evalgate.suite.v1`, `evalgate.report.v1`, `evalgate.check.v1`, `evalgate.rubric.v1`, `judge_verdict.v1`, `cassette.v1`, dataset, label and step-record schemas, exported to `schemas/` with a drift check.
- Python, HTTP (host allowlist) and LangGraph targets; asyncio runner with bounded concurrency, timeouts, retries with jitter and resume.
- Deterministic metrics (`exact`, `regex`, `json_schema`, `numeric_tolerance`, `contains_all`, `tool_calls`), custom metric plugins, and Ragas and DeepEval adapters.
- LLM judge with candidate isolation, position swap, injection guard, FakeJudge, cassettes and a provider gateway for Anthropic, Amazon Bedrock and OpenAI with PII redaction and a live budget hard stop.
- Judge calibration (agreement, Cohen's kappa, position inconsistency, verbosity bias, injection pass-through).
- Paired percentile bootstrap gate (10,000 resamples, seed 1337) with thresholds, cost and latency budgets and run health.
- DuckDB run store with migrations and a hash-chained gate audit; DuckDB response cache with read-only fallback.
- JSON, Markdown and self-contained HTML reports; Langfuse exporter; Promptfoo importer.
- Read-only report viewer (runs list, run detail, comparison) with light and dark themes, accessible at 375 px.
- Composite GitHub Action with an idempotent PR comment per suite, and CI, e2e, evals, docker, CodeQL, action self-test and release workflows.
- Toy targets (classify, extract, answer as v1, v2 and 50 variants), synthetic datasets (seed 1337), meta-evaluation, bootstrap coverage simulation and benchmarks.
- Docker images (distroless runtime), compose stack with observability and Langfuse profiles, and container test runs.

[Unreleased]: https://github.com/ROBERTG99/evalgate/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/ROBERTG99/evalgate/releases/tag/v0.1.0
