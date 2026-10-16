# ADR-0002: A thin provider gateway instead of LiteLLM

- Status: Accepted
- Date: 2026-10-16

## Context

The only AI component in evalgate is the judge pipeline. Every judge call must follow the same rules (build spec Appendix B and §4.5): PII is redacted before the call; model IDs come from configuration (`EVALGATE_JUDGE_MODEL`, `EVALGATE_JUDGE_HARD_MODEL`); output is structured JSON validated against `judge_verdict.v1`, and invalid output is an error, never a pass; only 408, 409, 429, 5xx and connection errors are retried, at most 3 attempts with jitter; a live run refuses to spend beyond `LIVE_EVAL_BUDGET_USD` and refuses a model with no price; there is no silent fallback to the fake judge inside a run; and every call can be recorded as a cassette and replayed offline.

Those rules only hold if there is exactly one place where requests leave the process. The library also has to stay small and fast to import (wheel < 1 MB, `import evalgate` < 300 ms) and its default install has to work offline with no provider SDK.

## Decision

All provider traffic goes through [src/evalgate/llm/gateway.py](../../src/evalgate/llm/gateway.py), the only module that imports `anthropic` or `openai`. It is a small module (293 lines, `wc -l`) with:

- a `Provider` protocol and three adapters: `AnthropicProvider` (Anthropic API, or Bedrock through `AsyncAnthropicBedrockMantle`), `OpenAIProvider`, and `FakeLLM` ([src/evalgate/llm/fake.py](../../src/evalgate/llm/fake.py)), selected by `EVALGATE_LLM_PROVIDER` (`fake` by default);
- SDK clients built with `max_retries=0`, so the gateway owns the retry policy (`MAX_ATTEMPTS = 3`, `RETRIABLE_STATUS = {408, 409, 429}` plus 5xx);
- `stop_reason` checks (`refusal`, `max_tokens`) before content is read, JSON Schema validation of every response, and an optional Pydantic validator;
- redaction ([src/evalgate/llm/redact.py](../../src/evalgate/llm/redact.py)), the spend guard ([src/evalgate/budget.py](../../src/evalgate/budget.py)), cost accounting from `pricing.yaml`, OpenTelemetry spans, and cassette recording ([src/evalgate/llm/cassette.py](../../src/evalgate/llm/cassette.py)).

Provider SDKs are optional extras (`evalgate[anthropic]`, `evalgate[bedrock]`, `evalgate[openai]`) imported lazily inside the adapters.

## Alternatives considered

- **LiteLLM (rejected).** It would give one call signature for many providers. It was rejected because:
  - It adds its own retry, fallback and routing layer. The gate's guarantees (retry only the listed statuses, at most 3 attempts, fail closed with `JudgeUnavailable`, never fall back silently) would then depend on a second policy that has to be configured and audited to match.
  - Claude-specific request features that the judge uses (structured output through `output_config.format`, explicit `output_config.effort`, adaptive thinking, prompt caching on the system block) are exercised directly through the official SDK, where their shapes are documented.
  - It is a large dependency with many transitive packages for a library whose wheel budget is 1 MB and whose dependencies must pass the license allowlist (`scripts/check_licenses.py`). Its install size and import time were not measured for this decision.
  - Budget enforcement, PII redaction and cassette keys still need one choke point in evalgate code, so LiteLLM would not remove the gateway, only move part of it.
- **Calling SDKs from the judge code directly (rejected).** It would spread retries, redaction and budgets across modules and break the "one importer" rule that `test_only_gateway_imports_provider_sdks` in [tests/unit/llm/test_gateway.py](../../tests/unit/llm/test_gateway.py) enforces.

## Consequences

### Positive

- One module to read and test for every rule that matters to the gate; a unit test fails if any other module imports a provider SDK.
- The default install has no provider SDK and makes no network calls; offline runs use `FakeLLM` and cassettes (NFR-5 measured 0 non-loopback connections during an offline judged run, `evals/reports/bench.json`, `make bench`).
- `import evalgate` measured 2.9737 ms (median of 5 fresh interpreters) and the wheel 0.1176 MB (NFR-6 and NFR-7, `evals/reports/bench.json`).

### Negative

- Each provider adapter is maintained by hand; supporting another provider means writing and testing a new adapter.
- No recorded cassettes exist yet, so the adapters are tested against response fixtures in the documented API shapes, not recordings ([docs/KNOWN_LIMITATIONS.md](../KNOWN_LIMITATIONS.md)).
- `ragas:` and `deepeval:` metrics that call an LLM use those libraries' own clients and bypass the gateway's cache, redaction, budget and socket guard ([docs/KNOWN_LIMITATIONS.md](../KNOWN_LIMITATIONS.md)).
