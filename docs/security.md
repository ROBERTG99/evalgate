# Security

evalgate runs suites (trusted configuration that can execute Python), calls HTTP targets and optional LLM
judges, stores results locally and serves a read-only viewer. This page is the threat model, the
controls and the scan results. Report vulnerabilities as described in [`SECURITY.md`](../SECURITY.md).

## Trust boundaries

| Input | Trust | Why |
|---|---|---|
| Suite YAML, rubric YAML, `plugins` | Trusted, like code | `python:` targets and plugins import and run code |
| Datasets, label files | Semi-trusted | Validated with Pydantic (`extra="forbid"`), size limits (`src/evalgate/suite/limits.py`) |
| Target output (HTTP, Python, LangGraph) | Untrusted | It reaches the judge, the reports, the viewer and the PR comment |
| Report JSON (viewer, `check`, baselines) | Untrusted | Validated against `evalgate.report.v1`, 50 MB cap |
| Judge (model) output | Untrusted | Validated against `judge_verdict.v1`; invalid output is an error, never a pass |

## STRIDE summary

| Threat | Example | Controls | Evidence |
|---|---|---|---|
| Spoofing | Someone pastes the `<!-- evalgate:report -->` markers into their own PR comment so the action edits it | Only comments by the bot account (`github-actions[bot]`, type Bot) are upserted | `tests/integration/test_pr_comment.py` |
| Tampering | Editing `gate_audit` rows or deleting the head of the chain | SHA-256 hash chain, anchors written by `evalgate gc`, `evalgate gc --verify-audit` | `tests/integration/store/test_store.py` |
| Tampering | Editing committed datasets or baselines | Append-only by version, enforced by `.claude/hooks/pre_tool_guard.py` and `MANIFEST.json` hashes | `tests/harness/test_hooks.py`, `tests/unit/generator/test_reproducible.py` |
| Repudiation | Who passed a gate with which baseline | `gate_audit` stores report and baseline SHA-256, git SHA, actor and decision | `src/evalgate/store/runstore.py` |
| Information disclosure | Provider keys or PII reaching reports, logs or providers | Secrets only from the environment, never written; the gateway redacts emails, phone numbers and Luhn-valid card numbers before a call | `tests/integration/test_secrets.py`, `tests/unit/llm/test_gateway.py` |
| Information disclosure | Viewer reads files outside the reports directory | Run ids matched against `^[0-9a-f-]{36}$`, static files allow-listed, symlinks out of the directory ignored | `tests/integration/viewer/test_security.py`, `tests/integration/viewer/test_pages.py` |
| Denial of service | Huge or deeply nested report, request floods | 1 MB per suite and dataset row, 50 MB per report, 100,000 cases, 50 requests/s per client, 30 s socket timeout, bounded comparison cache | `tests/unit/test_limits.py`, `tests/integration/viewer/test_security.py` |
| Elevation of privilege | SSRF through an `http:` target URL | `EVALGATE_HTTP_ALLOWED_HOSTS` allowlist, http/https only | `tests/unit/targets/test_http.py` |
| Elevation of privilege | XSS in the viewer or the HTML report | Jinja2 autoescape, CSP `default-src 'none'`, no inline script; the HTML report has no script at all | `tests/integration/viewer/test_pages.py::test_judge_output_labelled`, `tests/unit/report/test_markdown.py` |

## OWASP Top 10 for LLM applications (2025) mapped to evalgate

| Risk | Where it applies | Control |
|---|---|---|
| LLM01 Prompt injection | A target answer that tells the judge to pass it | Candidate isolation in escaped `<candidate_output>` tags after the instructions (`src/evalgate/judge/render.py`), injection patterns (`src/evalgate/judge/injection_patterns.yaml`) force a score of 0, 20 injected labels must never pass (`tests/unit/judge/test_judge.py::test_twenty_injected_candidates_never_pass`) |
| LLM02 Sensitive information disclosure | Case inputs sent to a provider | PII redaction in `src/evalgate/llm/redact.py`; data is synthetic |
| LLM03 Supply chain | Dependencies and images | `uv.lock`, pip-audit, license check, trivy, Dependabot, pinned tool versions |
| LLM04 Data and model poisoning | Tampered datasets or labels | Generated with seed 1337, hashes in `MANIFEST.json`, append-only versions |
| LLM05 Improper output handling | Judge output acted on | Schema validation (`judge_verdict.v1`); invalid output counts as a metric error and fails the gate closed |
| LLM06 Excessive agency | Not applicable | evalgate runs no agent and executes no model-proposed action |
| LLM07 System prompt leakage | Judge prompts | Prompts are public files in `prompts/`; no secrets in prompts |
| LLM08 Vector and embedding weaknesses | Not applicable | No embeddings; the toy RAG retriever is keyword based |
| LLM09 Misinformation | Over-trusting an LLM judge | Judges are adopted only after calibration (`evalgate calibrate`); judge results are labelled "AI judge" with rubric version |
| LLM10 Unbounded consumption | Live judge costs | Cost estimate printed first, exit 3 before any call when over `LIVE_EVAL_BUDGET_USD`, spend guard during the run, unpriced models refused |

## PR comment injection

Target output reaches the PR comment through case ids, errors and judge reasons. `src/evalgate/report/markdown.py`
escapes Markdown and HTML-significant characters, cuts excerpts at 200 characters, breaks `@mentions` and
autolinks, and code spans cannot contain backticks or pipes. GitHub workflow commands (`::error`) escape
`%`, CR and LF.

## Viewer

Read-only (POST, PUT, PATCH and DELETE return 405), binds `127.0.0.1` unless `--host` says otherwise (the
container binds `0.0.0.0` inside its network namespace and compose publishes it on `127.0.0.1:8100` only),
and requires `Authorization: Bearer <token>` when `EVALGATE_SERVE_TOKEN` is set (`/healthz` stays open for
health checks). A report over 50 MB is never read; it appears in the error panel with status 413.

## Scan results

`make security` (`scripts/security.sh`) runs gitleaks over the working tree and history, bandit on `src/`,
pip-audit on the locked dependencies (all extras), the license check (`scripts/check_licenses.py`) and trivy on
both images, failing on high or critical findings. `make sbom` writes a CycloneDX SBOM of the locked environment to `dist/sbom.cdx.json`; the release workflow attaches it to the GitHub Release. Last result: see [`docs/verification.md`](verification.md).

### Dependency findings

| Finding | Package | Why it is accepted | Revisit |
|---|---|---|---|
| PYSEC-2026-2447 (pickle deserialisation from a writable cache directory) | `diskcache` 5.6.3, pulled in only by the optional `[ragas]` extra | evalgate never imports diskcache; exploitation needs write access to the user's own cache directory; no fixed release exists | When diskcache or ragas publish a fix |
| PYSEC-2026-3046 (file and URL handling in ragas' multimodal faithfulness collection) | `ragas` 0.4.3, optional `[ragas]` extra | evalgate's adapter uses the text `SingleTurnSample` metrics from `ragas.metrics`, never the multimodal collection; no fixed release exists | When ragas publishes a fix |

Neither package is in the default install or the Docker images.
