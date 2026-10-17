---
paths:
  - "tests/**"
---

# Testing

- Write the failing test first. Name tests after the behaviour (`test_timeout_scores_zero`).
- No network: `pytest-socket` is on; only loopback is allowed. Use random ports (`port=0`).
- Fixed seeds; factories in `tests/factories.py`; no wall-clock assertions under 100 ms.
- Never skip, xfail or weaken a test to get green; fix the code or document the gap.
- Contract tests talk to WireMock-compatible doubles; E2E tests use Playwright with axe.
