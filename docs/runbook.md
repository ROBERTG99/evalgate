# Runbook

Operations for evalgate maintainers: alerts, releases, baselines, the audit chain, the local stack and live evals. The Prometheus alerts in [`deploy/prometheus/alerts.yml`](../deploy/prometheus/alerts.yml) link to the first three sections by anchor; keep those headings unchanged. The alert rules are unit-tested by `promtool test rules` on [`deploy/prometheus/alerts.test.yml`](../deploy/prometheus/alerts.test.yml) (run in `make test-docker`).

The alerts need the `observability` compose profile: Prometheus (`http://localhost:8191`) scrapes `toy-targets:8110/metrics` directly and reads `evalgate_*` metrics from the OTel collector's Prometheus exporter (`otel-collector:8889`). evalgate only exports metrics when `--otel` is passed or `OTEL_EXPORTER_OTLP_ENDPOINT` is set and the `otel` extra is installed, for example:

```bash
docker compose --profile observability up -d
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:8181 uv run evalgate run evals/suites/classify.yaml --split test --out /tmp/classify.json
```

## Toy target errors

**What fires.** `ToyTargetErrorRate` (severity `warning`):

```text
sum(rate(toy_requests_total{status!~"2.."}[5m])) / clamp_min(sum(rate(toy_requests_total[5m])), 1e-9) > 0.01
for: 5m
```

More than 1% of toy-target requests over a 5-minute rate window returned a non-2xx status, and the condition held for 5 minutes. The threshold is 1% for 5 minutes.

**Why it matters.** Target errors become case errors with metric values 0. Above 50% errored cases the run is marked `run_health: degraded` and the gate fails, so a toy-target outage looks like a quality regression in the meta-evaluation, the demo and CI.

**Diagnose.**

```bash
docker compose ps toy-targets                                   # health status
docker compose logs --tail 200 toy-targets                      # tracebacks
curl -s http://localhost:8110/healthz
curl -s http://localhost:8110/metrics | grep toy_requests_total # counts by endpoint, version, status
```

In Prometheus, `sum by (endpoint, version, status) (rate(toy_requests_total[5m]))` shows which endpoint and status code dominate. A middleware in `examples/toy-targets/src/toy_targets/app.py` counts every final status: `200`, the `400` for an unknown `X-Toy-Version` or `X-Toy-Variant` header (`version="invalid"`), request-validation errors (`422`), unknown paths (`endpoint="other"`, `404`) and crashes (`500`). A target that is down sends nothing at all, so also check `up{job="toy-targets"}` and the container logs. Common causes:

- `400` responses: a wrong `EVALGATE_TOY_VERSION` (only `v1` and `v2` exist) or a variant id missing from `evals/datasets/meta/variants.v1.jsonl`.
- Missing traffic or `up == 0`: the container is restarting or out of memory; check `docker compose logs` and `docker stats`.
- Errors in the evalgate report but not in the counter: a suite with the wrong path or body shape (`{"text"}`, `{"document"}`, `{"question"}`), or a host not in `EVALGATE_HTTP_ALLOWED_HOSTS`; read `cases[].error` in the report.

**Fix.** Correct the header or suite target; restart with `docker compose up -d --build --wait toy-targets`. If port 8110 is held by a leftover host process (`uv run toy-targets`), stop it (`pkill -f toy-targets`) before starting the stack. Re-run the affected suite and confirm `run_health` is `ok` in the report.

## Judge cache

**What fires.** `JudgeCacheHitLow` (severity `info`):

```text
sum(increase(evalgate_cache_hits_total[1h])) / clamp_min(sum(increase(evalgate_judge_calls_total[1h])), 1)
  < 0.5 and sum(increase(evalgate_judge_calls_total[1h])) > 0
for: 15m
```

Over the last hour, fewer than half of the judge calls were served from `cache.duckdb`, there was at least one judge call, and this held for 15 minutes. The intended condition is "< 50% on re-runs"; the rule measures a 1-hour window, so the first run of a new suite or prompt version can trigger it on its own.

**Why it matters.** On an unchanged re-run every judge call should be a cache hit (FR-10: zero provider calls). Misses cost money and time in live mode, and in offline mode they mean the cache is not being reused.

**Diagnose.**

- Read the run's counters: `evalgate run` prints `judge calls N, cache hits N, provider calls N`, and the report holds `extensions.judge_calls`, `extensions.cache_hits` and `extensions.provider_calls`.
- Check the cache mode: `--cache off` or `--cache ro` on the command line, or a warning that the cache was locked for 5 s and fell back to read-only.
- Check that the cache file survived: it is `$EVALGATE_HOME/cache.duckdb` (default `.evalgate/cache.duckdb`). In CI it only persists through the 14-day `eval-reports` artifact (`.github/workflows/evals.yml`); a fresh runner starts with an empty cache.
- Check what changed in the key. The key is `sha256(route | model | prompt_version | canonical messages and schema)`, so a new prompt version, model (`EVALGATE_JUDGE_MODEL`, `EVALGATE_JUDGE_HARD_MODEL`), rubric or candidate text produces misses by design. A row whose `request_digest` differs (a prompt edited without a version bump) is treated as stale.
- Check the mode namespace: offline runs never reuse live verdicts and live runs never reuse offline ones.
- Inspect the cache read-only:

```bash
uv run python -c "import duckdb; c = duckdb.connect('.evalgate/cache.duckdb', read_only=True); print(c.sql('SELECT route, model, prompt_version, count(*), sum(hits) FROM responses GROUP BY ALL'))"
```

**Fix.** Re-run with `--cache rw` (the default); restore or keep the cache artifact between CI runs; bump the prompt version file instead of editing a released prompt; make sure no other process holds `cache.duckdb` open in write mode. Rows older than `EVALGATE_CACHE_TTL_DAYS` (default 90) are ignored and pruned by `evalgate gc`.

## Gate flapping

**What fires.** `GateFlapping` (severity `warning`):

```text
changes(evalgate_gate_last_decision[6h]) >= 3
```

The gauge `evalgate_gate_last_decision{suite}` is set by every `evalgate check` (1 pass, 0 fail). The alert fires when one series changed value 3 or more times within the last 6 hours. There is no `for:` clause, so it fires on the first evaluation that sees the third change.

**Window.** The rule uses a 6-hour time window (`[6h]`). The intended condition is "3 decision changes in 5 runs", a count-based window that PromQL cannot express on a gauge, so the 6-hour window is an approximation. It matches the intent only when about 5 gate runs of a suite happen within 6 hours: for a suite checked much less often the alert stays silent even if every run flips, and for one checked much more often 3 changes spread over many more than 5 runs still fire it. The promtool test feeds one series per suite at 30-minute intervals (`1 0 1 0 1`) and expects the alert for `classify` at 2 hours.

**Why it matters.** A gate that alternates between pass and fail on similar inputs is not trustworthy: either the inputs are nondeterministic, or a metric sits on its threshold and noise moves it across.

**Diagnose.**

- In Prometheus: `changes(evalgate_gate_last_decision[6h])` and `evalgate_gate_decisions_total` by `suite` and `decision`. Metrics carry no per-process `service.instance.id` (traces do), so successive `evalgate check` processes write the same `evalgate_gate_last_decision{suite}` series and `changes()` sees the flips; `count by (suite) (evalgate_gate_last_decision)` should be 1 per suite.
- In the run store, read the recent decisions (the audit chain is append-only; read it, never edit it):

```bash
uv run python -c "import duckdb; c = duckdb.connect('.evalgate/runs.duckdb', read_only=True); print(c.sql('SELECT seq, ts, decision, git_sha, failures FROM gate_audit ORDER BY seq DESC LIMIT 10'))"
```

- Compare a passing and a failing run in the viewer (`http://localhost:8100/compare?base=<run_id>&cand=<run_id>`) or with `evalgate check <failing.json> --baseline <passing.json>`.
- Typical causes: a metric value within a few cases of its threshold (`reason: threshold` alternating), a CI that straddles 0 near `--max-regression-pp` (`reason: regression` alternating), latency near `max_p95_ms` (`budget_p95`), live judge verdicts that vary between runs, a target that is not deterministic, or `run_health: degraded` from intermittent target errors (see [Toy target errors](#toy-target-errors)).

**Fix.** Make the inputs deterministic first: offline mode or a warm judge cache, fixed `EVALGATE_BOOTSTRAP_SEED` (default 1337), pinned target version. If the metric really sits on its threshold, add test cases (more paired cases narrow the interval) rather than lowering the threshold; thresholds are only ever raised. Record any change of threshold or budget in `docs/DECISIONS.md`.

## Release

Releases are cut from a local tag; pushing the tag is a maintainer action (the development hooks block tag pushes and `gh release create`).

1. Run `make verify` with no API keys set; it must pass.
2. Set the version in `pyproject.toml` (`[project] version = "x.y.z"`) and keep `__version__` in `src/evalgate/__init__.py` equal to it.
3. Add a `## [x.y.z] - YYYY-MM-DD` section to `CHANGELOG.md`. `release.yml` checks `grep -q "^## \[x.y.z\]" CHANGELOG.md` and uses that section as the release notes.
4. Build and check locally: `make build` (wheel and sdist, 1 MB budget) and `make sbom` (`dist/sbom.cdx.json`).
5. Commit (`chore(release): vx.y.z`, no attribution trailers) and create the annotated tag locally: `git tag -a vx.y.z -m "evalgate vx.y.z"`.
6. Maintainer: push the tag with `git push origin vx.y.z`.

The push triggers [`.github/workflows/release.yml`](../.github/workflows/release.yml):

- `build`: fails unless `v$(uv version --short --package evalgate)` equals the tag and `CHANGELOG.md` has the section; runs `make build` and `make sbom`; uploads `dist/` for 30 days.
- `github-release`: `gh release create` with the wheel, the sdist and `sbom.cdx.json`, notes taken from the CHANGELOG section.
- `pypi`: PyPI trusted publishing (`pypa/gh-action-pypi-publish`, OIDC `id-token: write`, environment `pypi`). The PyPI project must list this repository, workflow `release.yml` and environment `pypi` as a trusted publisher; no API token is stored.
- `images`: builds `docker/evalgate.Dockerfile` and `docker/toy-targets.Dockerfile` and pushes `ghcr.io/<owner>/evalgate:vx.y.z` and `ghcr.io/<owner>/toy-targets:vx.y.z`.

Users pin the action with `uses: ROBERTG99/evalgate/action@vx.y.z`, so a published tag is a contract.

## Rolling back a tag

Never move, delete and re-create, or force-push a published tag: action users and PyPI already reference it, and PyPI does not accept a second upload of the same version.

1. Delete the GitHub Release so the broken assets are no longer offered: `gh release delete vx.y.z` (maintainer). Leave the tag in place.
2. Yank the version on PyPI (project page, Manage, the release, Options, Yank) with a reason. Yanked versions stay installable only when pinned exactly.
3. Optionally delete the GHCR image versions `evalgate:vx.y.z` and `toy-targets:vx.y.z` from the package settings.
4. Fix forward: release `x.y.(z+1)` through [Release](#release), with a CHANGELOG entry that names the broken version and the fix.

## Baseline rotation

Baselines in `evals/baselines/` are append-only. A committed baseline is never edited; the `pre_tool_guard.py` hook blocks edits from the AI-assisted development setup, and `DECISIONS.md` records how each one was made. Rotate a baseline only when the reference behaviour changes on purpose (a new v1 target, a new dataset version or a new metric), never to make a failing gate pass.

1. Start the v1 toy targets: `docker compose up -d --wait` (or `uv run --frozen toy-targets --port 8110`).
2. Create the new versioned file on the `test` split, offline, without the cache:

   ```bash
   EVALGATE_TOY_VERSION=v1 uv run evalgate run evals/suites/<suite>.yaml --split test --cache off --out evals/baselines/<suite>.vN.json
   ```

   The existing files are the unversioned first generation (`evals/baselines/<suite>.json`), so the first rotation writes `<suite>.v2.json`. Keep `EVALGATE_LLM_PROVIDER` unset (`fake`) so the baseline is offline.
3. Compare it with the previous baseline and read the deltas: `uv run evalgate check evals/baselines/<suite>.vN.json --baseline evals/baselines/<suite>.json`.
4. Point every reference at the new file: `.github/workflows/evals.yml` (`baseline:`), `.github/workflows/action-selftest.yml` (classify), `scripts/run_evals.py`, `scripts/meta_eval.py`, `scripts/demo.sh` (classify) and `scripts/build_eval_report.py`.
5. Run `make eval` and `make meta-eval`; both must pass.
6. Add a row to `docs/DECISIONS.md` with the date, the command, the toy-target version, the git SHA and the reason.

## Audit chain

Every `evalgate check` appends a row to `gate_audit` in `$EVALGATE_HOME/runs.duckdb` with the report and baseline SHA-256, git SHA, decision, failures and actor (`GITHUB_ACTOR` or `USER`). Each row stores `prev_hash` and `hash = sha256(prev_hash + canonical_json(row))`.

```bash
uv run evalgate gc --verify-audit
```

It prints `evalgate: gate audit chain verified` or `evalgate: gate audit chain broken at seq N` and exits 1. When retention has pruned the head (rows older than 365 days), verification continues from the `audit_anchor` row that `evalgate gc` wrote, so retention is not reported as tampering but deleting head rows by hand is. After verifying, the same command applies retention: runs older than `--keep-days` (default 30), audit rows older than 365 days and cache rows older than `EVALGATE_CACHE_TTL_DAYS`. Pass a larger `--keep-days` to keep more runs.

If the chain is broken: copy `runs.duckdb` aside before anything else, read rows around seq N with a read-only connection (see [Gate flapping](#gate-flapping) for the query), compare `report_sha256` with the report files you still have, and do not repair rows in place. The chain only covers checks run on the same machine; CI keeps `runs.duckdb` as a 14-day artifact and there is no central audit store ([`KNOWN_LIMITATIONS.md`](KNOWN_LIMITATIONS.md)).

## Local stack

| Command | What it does |
|---|---|
| `make up` | `docker compose up -d --build --wait`, then `make seed` |
| `make seed` | `docker compose --profile tools run --rm seed`: v1 and v2 runs of the three suites into the `reports` volume |
| `make demo` | `scripts/demo.sh`: classify v2 gated against the v1 baseline (exit 1), then v1 (exit 0), offline; reports in `.evalgate/demo/` |
| `make logs` | `docker compose logs -f` |
| `make down` | `docker compose down` (keeps volumes; add `-v` by hand to drop the seeded reports) |
| `make test-docker` | Starts and seeds the stack, then runs `compose.test.yaml` (tests, e2e, promtool) |
| `make clean` | Both compose projects down with volumes, plus build outputs and `.evalgate/` |

Ports (all bound to `127.0.0.1`): viewer 8100, toy targets 8110; with `--profile observability`: OTLP 8180 (gRPC) and 8181 (HTTP), Grafana 8190, Prometheus 8191, Jaeger 8192; with `--profile langfuse`: Langfuse 8193, Postgres 8120, Redis 8130, ClickHouse 8140, MinIO 8141; test stack: WireMock Langfuse 8142, WireMock GitHub 8143. The viewer answers `GET /healthz`; a request with a `Host` header that is not loopback or listed in `EVALGATE_SERVE_ALLOWED_HOSTS` gets 421, and `EVALGATE_SERVE_TOKEN` turns on bearer-token auth.

## Live evals and budget

`make eval-live` runs `scripts/eval_live.py`: it calibrates `answer_correctness.v1` on its test labels with a real judge (`EVALGATE_LLM_PROVIDER`, default `anthropic` in this script; `EVALGATE_JUDGE_MODEL`, default `claude-haiku-5-5`).

- Without the provider key it writes `evals/reports/live-eval.json` with `"ran": false` and exits 2.
- It prints the estimate (4 calls per labelled item: position swap and verbosity probe) against `LIVE_EVAL_BUDGET_USD` (default 2). If the estimate is over budget it exits 3 before any provider call.
- During the run the gateway keeps a hard stop at the same budget (exit 3). A judge model without a price in `src/evalgate/pricing.yaml` is refused with exit 3 before any call.
- On success it records `cost_usd` and the calibration result in `live-eval.json`, and exits 0 when calibration passes, 1 when it does not.

```bash
export ANTHROPIC_API_KEY=...        # never commit it; .env is gitignored
LIVE_EVAL_BUDGET_USD=1 make eval-live
make record-fixtures                 # same run with EVALGATE_RECORD_CASSETTES=1
```

The same estimate-then-stop rule applies to `evalgate run` with a live provider: exit 3 before any provider call when the estimate is over `LIVE_EVAL_BUDGET_USD`.
