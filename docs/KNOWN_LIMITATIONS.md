# Known limitations

What is not done, or done with a documented gap. Each entry names the reason.

- **Third-party LLM metrics bypass the gateway.** `ragas:` and `deepeval:` metrics that call an LLM use those libraries' own clients, so they skip evalgate's cache, PII redaction, `LIVE_EVAL_BUDGET_USD` and the offline socket guard. Use their non-LLM metrics in gates (ExactMatch, StringPresence, NonLLMStringSimilarity, BLEU/ROUGE; DeepEval ExactMatchMetric, PatternMatchMetric); the offline test suite only exercises those.
- **Release binaries are not checksum-verified.** `scripts/install_tools.sh` downloads hadolint, trivy and shellcheck over HTTPS from GitHub releases by pinned version but does not verify SHA-256 sums; actionlint and gitleaks are built from the Go module proxy, which is checksum-verified by `sum.golang.org`.
- **No recorded LLM cassettes.** No provider key was available during the build, so `tests/fixtures/llm/` holds no cassettes and the provider adapters are tested against response fixtures written in the documented API shapes (`tests/fixtures/provider_responses/`), not recordings.
- **Judge labels are by construction.** All 260 judge labels were generated with known answers; the maintainer review of 40 labels is pending (see `PROGRESS.md`). See ADR-0006 for what this does and does not prove.
- **`gate_audit` only covers `evalgate check` runs on the same machine.** CI keeps `runs.duckdb` as a 14-day artifact; there is no central audit store.
