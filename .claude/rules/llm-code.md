---
paths:
  - "src/evalgate/llm/**"
  - "src/evalgate/judge/**"
  - "prompts/**"
  - "scripts/eval_live.py"
---

# LLM code (Appendix B of the build spec)

- Only `src/evalgate/llm/gateway.py` imports provider SDKs (`anthropic`, `openai`).
- Model IDs come from configuration; defaults `claude-haiku-5-5` (judge) and `claude-opus-5-5` (judge_hard). No date suffixes.
- Structured output through `output_config.format` with a JSON schema; validate with Pydantic; invalid output is an error, never a pass.
- Adaptive thinking with explicit `output_config.effort` per route; never `budget_tokens`; no assistant prefill; never force `tool_choice`.
- Check `stop_reason` (`refusal`, `max_tokens`) before reading content.
- Retry only 408, 409, 429, 5xx and connection errors, with backoff and jitter, at most 3 attempts.
- Prompts live in versioned files `prompts/<name>.v<N>.md`; bump the version instead of editing a released prompt.
- Every call records prompt version, model, tokens, cost, latency and outcome; PII is redacted before the call.
- Tests use FakeLLM and cassettes only, never a live provider.
