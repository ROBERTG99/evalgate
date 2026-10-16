# Design FAQ

Short answers to the design questions of the build specification (`docs/specs/000-build-spec.md`, §18). Every claim points at the code that implements it, and every number comes from a code constant or a report in `evals/reports/` written by the `make` target named next to it (the reports are generated and gitignored; `evals/REPORT.md` is the committed summary).

## 1. Why a paired bootstrap with 10,000 resamples?

Baseline and candidate run the same cases, and a case that is hard for one version is usually hard for the other. Resampling the per-case differences together (`candidate - baseline`) removes that shared difficulty from the interval, so a paired interval is narrower than comparing two independent means; how much narrower depends on how strongly the runs agree per case [bootstrap.py:51](../src/evalgate/stats/bootstrap.py#L51). A percentile bootstrap needs no normality assumption, which matters because most metrics are binary or bounded in [0, 1] and often sit near 1.0 (the rejected alternative, a paired t-test, is in [ADR-0003](adr/0003-paired-bootstrap.md)).

10,000 resamples is the default [bootstrap.py:10](../src/evalgate/stats/bootstrap.py#L10): a conventional size that keeps resampling noise in the interval ends small, and still cheap. `make bench` measured 0.0374 s for 200 cases x 10,000 resamples over 2 metrics against a 2 s budget (`evals/reports/bench.json`). Resampling uses numpy `PCG64` with a fixed seed [bootstrap.py:44](../src/evalgate/stats/bootstrap.py#L44) (`EVALGATE_BOOTSTRAP_SEED`, default 1337 [config.py:35](../src/evalgate/config.py#L35)), so the same reports always give the same verdict.

The coverage simulation [simulation.py:12](../src/evalgate/stats/simulation.py#L12) checks the interval: over 400 simulated datasets of 150 correlated binary cases, 96% of the 95% intervals contained the true delta (`evals/reports/bootstrap-coverage.json`, scenario `primary_n150_binary`). The same file shows under-coverage at small n (0.8425 for 20 cases, 0.8875 for 60 cases with a near-perfect baseline), recorded in `docs/KNOWN_LIMITATIONS.md`.

## 2. How are multiple comparisons handled?

They are not adjusted. Each gated metric is compared on its own with a 95% interval: `check` loops over the report's metrics and applies `is_regression` to each one independently [gate.py:112](../src/evalgate/stats/gate.py#L112). There is no Bonferroni, Holm or false-discovery-rate correction.

The consequence: each test has a nominal one-sided false-alarm rate of 2.5%, and with several gated metrics at the margin the chance that at least one of them shows a false regression is higher. The `extract` suite gates 6 metrics [extract.yaml:9](../evals/suites/extract.yaml#L9). Two things soften this without removing it: a regression must also exceed `--max-regression-pp` (question 3), and metrics computed from the same outputs tend to move together. The meta-evaluation saw 0 false alarms in 20 neutral changes, but the exact 95% upper bound is 0.1684 (`evals/reports/meta-eval.json`). The gap is listed in [KNOWN_LIMITATIONS.md:11](../docs/KNOWN_LIMITATIONS.md#L11).

## 3. When is a regression "statistically supported"?

When both conditions of `is_regression` hold [gate.py:49](../src/evalgate/stats/gate.py#L49): the observed delta is worse than `-max_regression_pp` (default 1.0 pp [gate.py:62](../src/evalgate/stats/gate.py#L62)), and the 95% interval excludes 0 on the worse side [gate.py:53](../src/evalgate/stats/gate.py#L53). For `direction: lower` metrics the test is mirrored. A drop that is significant but smaller than the margin passes; a drop larger than the margin whose interval still crosses 0 also passes.

Cases are paired by case id, and only cases scored in both reports count [gate.py:27](../src/evalgate/stats/gate.py#L27). With fewer than `MIN_PAIRED = 10` pairs [gate.py:12](../src/evalgate/stats/gate.py#L12), or a gated metric the baseline lacks, the gate fails closed with reason `error` instead of claiming either way [gate.py:119](../src/evalgate/stats/gate.py#L119).

## 4. How are judges calibrated, and what limits synthetic labels?

`evalgate calibrate` runs the judge over the labelled items of one rubric and split (default `test`; rubric work iterates on `dev`) [calibrate.py:117](../src/evalgate/judge/calibrate.py#L117). It reports agreement, Cohen's kappa [calibrate.py:29](../src/evalgate/judge/calibrate.py#L29), the confusion matrix, position inconsistency, verbosity bias, injection pass-through and judge errors, and passes only when every check holds [calibrate.py:151](../src/evalgate/judge/calibrate.py#L151). Default thresholds are agreement at least 0.8, kappa at least 0.7, position inconsistency at most 0.10 and absolute verbosity bias at most 0.05 [judge.py:16](../src/evalgate/contracts/judge.py#L16); injection pass-through must be exactly 0. Offline, `answer_correctness.v1` scores agreement 0.875 and kappa 0.746283 on 64 test items (`evals/reports/calibration-answer_correctness.json`), `pairwise_preference.v1` 0.875 and 0.811765 on 16 (`evals/reports/calibration-pairwise_preference.json`), and `rubric_adherence.v1` 0.916667 and 0.823529 on 24 (`evals/reports/calibration-rubric_adherence.json`).

The labels are generated by construction from the synthetic FAQ facts [judge.py:1](../data/generator/judge.py#L1): each item is built to be correct, wrong, padded or injected, so its label is known without a human. That proves the judge tracks the constructed property and catches harness bugs (swapped labels, broken parsing, injection pass-through). It does not prove agreement with human judgment on natural answers: the items share the generator's idea of correctness, and the offline numbers above measure the rule-based FakeJudge (model `fake-judge`), whose rules resemble that idea. A few construction types are made hard on purpose (numbers as words, negations, unusual citations) so agreement cannot be perfect. [ADR-0006](adr/0006-labels-by-construction.md) records the decision and this limit, and the pending maintainer review of 40 labels is tracked in [KNOWN_LIMITATIONS.md:8](../docs/KNOWN_LIMITATIONS.md#L8).

## 5. How are position and verbosity bias measured?

Position: rubrics have `position_swap: true` by default [judge.py:34](../src/evalgate/contracts/judge.py#L34), so every item is judged twice, `AB` and `BA` for pairwise rubrics and reference-before and reference-after the candidate for pointwise ones [metric.py:75](../src/evalgate/judge/metric.py#L75). The second pairwise verdict is mirrored back [metric.py:102](../src/evalgate/judge/metric.py#L102); when the two verdicts differ the case is `position_inconsistent`, scores 0.5 and is counted [metric.py:115](../src/evalgate/judge/metric.py#L115). Calibration reports the share of such items [calibrate.py:108](../src/evalgate/judge/calibrate.py#L108), and run reports carry the per-metric count in `extensions.judge` [context.py:221](../src/evalgate/judge/context.py#L221).

Verbosity: with `verbosity_probe: true`, calibration judges every item a second time with a neutral padding prefix of about 20 words and no facts [calibrate.py:24](../src/evalgate/judge/calibrate.py#L24) and reports the mean score shift [calibrate.py:100](../src/evalgate/judge/calibrate.py#L100). A positive value means padding alone raised scores. Both measures are 0.0 in the three offline calibration reports, which is expected of a rule-based judge; they become informative with a live model (`make eval-live`), which has not run yet: `evals/reports/live-eval.json` records `ran: false` because no API key was set.

## 6. Why can a target output not hijack the judge?

Four layers, in order:

- Screening: before any judge call the candidate is matched against the patterns in [injection_patterns.yaml:3](../src/evalgate/judge/injection_patterns.yaml#L3) (for example "ignore the rubric", `system:`, the judge's own tag names, `judge_verdict`). A match scores 0 with verdict `fail` and is counted as blocked [metric.py:68](../src/evalgate/judge/metric.py#L68).
- Isolation: instructions live only in the system prompt; the candidate goes into the user message, HTML-escaped inside `<candidate_output>` tags [render.py:53](../src/evalgate/judge/render.py#L53), so it cannot close a tag or pose as the rubric [render.py:23](../src/evalgate/judge/render.py#L23).
- Constrained output: the verdict must match a JSON schema with a fixed verdict enum, fixed criteria keys and no extra properties [render.py:75](../src/evalgate/judge/render.py#L75), validated client-side by the gateway [gateway.py:281](../src/evalgate/llm/gateway.py#L281). Unusable output becomes a metric error, which fails the gate rather than passing it (question 9).
- Calibration: a rubric is adopted only with injection pass-through 0 [calibrate.py:136](../src/evalgate/judge/calibrate.py#L136); the `answer_correctness` test split has 8 injection items and 0.0 pass-through (`evals/reports/calibration-answer_correctness.json`).

The pattern list is not exhaustive; a paraphrased injection that avoids it still faces tag isolation, the schema and position swap.

## 7. Why DuckDB?

It is one embedded file with no server to run, and the store's work is analytical SQL over runs, cases, scores and steps. The run store (`runs.duckdb`) and the response cache (`cache.duckdb`) share one connection helper and ordered migrations, each applied in a transaction [db.py:40](../src/evalgate/store/db.py#L40). SQLite and Postgres were the rejected alternatives ([ADR-0001](adr/0001-duckdb.md)).

DuckDB allows one writer per file, so the code plans for contention: `connect` retries a locked file for up to 5 s [db.py:16](../src/evalgate/store/db.py#L16), the cache then falls back to read-only and then to off [__init__.py:49](../src/evalgate/cache/__init__.py#L49), and a run store that cannot open never stops the report from being written [engine.py:120](../src/evalgate/runner/engine.py#L120). Writes are blocking, so the runner moves them off the event loop [engine.py:280](../src/evalgate/runner/engine.py#L280). The store also holds the hash-chained `gate_audit` [runstore.py:26](../src/evalgate/store/runstore.py#L26).

## 8. How is the cache keyed and invalidated?

The key is the cassette key, `sha256(route | model | prompt_version | canonical_json(messages, schema_name))` [cassette.py:17](../src/evalgate/llm/cassette.py#L17). The user message contains the rubric name, version and criteria plus the escaped input, reference and candidate, so a change to any of them, to the judge model or to the prompt version (the `judge_<rubric>.vN.md` file name) is a new key.

Invalidation:

- Stale prompt: each row also stores a `request_digest` over the system prompt, schema, effort and token limit [cassette.py:27](../src/evalgate/llm/cassette.py#L27). A row whose digest differs from the current request is ignored, so a prompt edited without a version bump does not serve old verdicts [context.py:205](../src/evalgate/judge/context.py#L205).
- Mode: live runs reuse only live verdicts and offline runs only offline ones [context.py:203](../src/evalgate/judge/context.py#L203).
- Age: rows older than `EVALGATE_CACHE_TTL_DAYS` (default 90 [config.py:76](../src/evalgate/config.py#L76)) are not returned [__init__.py:78](../src/evalgate/cache/__init__.py#L78) and `gc` deletes them [__init__.py:140](../src/evalgate/cache/__init__.py#L140).

Rows are inserted once (`ON CONFLICT DO NOTHING`); only a live response may replace an existing row [__init__.py:118](../src/evalgate/cache/__init__.py#L118). Target responses are cached only with `--cache-targets`, keyed by suite, target description and case input [engine.py:78](../src/evalgate/runner/engine.py#L78).

## 9. What happens when a provider fails mid-run?

The gateway retries only timeouts, connection errors and HTTP 408, 409, 429 and 5xx [gateway.py:31](../src/evalgate/llm/gateway.py#L31), up to `MAX_ATTEMPTS = 3` with full-jitter backoff capped at 8 s [gateway.py:304](../src/evalgate/llm/gateway.py#L304). A non-retriable error, or three failed attempts, raises `JudgeUnavailableError` [gateway.py:305](../src/evalgate/llm/gateway.py#L305). There is no silent fallback to the fake provider.

The judge metric turns that error (and unusable output: refusal, truncation, invalid JSON) into a score of 0 marked `metric_error` [metric.py:99](../src/evalgate/judge/metric.py#L99), and the run goes on. The report counts metric errors per metric [engine.py:388](../src/evalgate/runner/engine.py#L388), and `check` fails any gated metric with at least one error, reason `error` [gate.py:86](../src/evalgate/stats/gate.py#L86). An outage can make the gate fail, never pass. A budget abort (exit 3) is the one error that stops the whole run [metric.py:95](../src/evalgate/judge/metric.py#L95).

Target failures follow the same idea: retries with backoff [retry.py:28](../src/evalgate/runner/retry.py#L28), then the case is recorded with its error; above a 0.5 error rate the run is `degraded` [engine.py:31](../src/evalgate/runner/engine.py#L31) and the gate fails [gate.py:88](../src/evalgate/stats/gate.py#L88). Finished cases are written to the run store as they complete, so `evalgate run --resume <run_id>` skips the finished ones and runs errored ones again [engine.py:310](../src/evalgate/runner/engine.py#L310), and cached verdicts are not paid for twice.

## 10. How are budgets enforced?

At three points:

- Before a live run: the judge context estimates `cases x calls per case` (2 with position swap) at 1,200 input and 300 output tokens per call [budget.py:13](../src/evalgate/budget.py#L13), prints the estimate and exits 3 before any provider call when it exceeds `LIVE_EVAL_BUDGET_USD` (default 2.0 [config.py:80](../src/evalgate/config.py#L80)) [budget.py:49](../src/evalgate/budget.py#L49). A judge model with no price in `pricing.yaml` is refused the same way, since it would make the budget unenforceable [context.py:139](../src/evalgate/judge/context.py#L139). `make bench` estimated 0.0324 USD for 120 judge calls (`evals/reports/bench.json`).
- During a live run: `SpendGuard` keeps a thread-safe running total [budget.py:54](../src/evalgate/budget.py#L54); the gateway checks it before every call [gateway.py:249](../src/evalgate/llm/gateway.py#L249) and adds the priced cost after [gateway.py:279](../src/evalgate/llm/gateway.py#L279). Calls already in flight (at most `EVALGATE_JUDGE_CONCURRENCY`, default 4 [config.py:51](../src/evalgate/config.py#L51)) can finish, so spend can pass the budget by those calls.
- In the gate: a suite's `budget.max_cost_usd` and `budget.max_p95_ms` fail the check with reasons `budget_cost` and `budget_p95` (exit 1) [gate.py:97](../src/evalgate/stats/gate.py#L97). Cost comes from per-step token prices [accounting.py:27](../src/evalgate/accounting.py#L27).

## 11. How is offline mode proven network-free?

Offline is the default: the provider is `fake` unless `EVALGATE_LLM_PROVIDER` says otherwise [config.py:64](../src/evalgate/config.py#L64), and provider SDKs are imported only inside the gateway's live providers [gateway.py:65](../src/evalgate/llm/gateway.py#L65).

The proof is in the tests. Every pytest run uses `pytest-socket` with `--disable-socket --allow-unix-socket --allow-hosts=127.0.0.1,localhost,::1` [pyproject.toml:122](../pyproject.toml#L122), and a test confirms the guard is on by connecting to a TEST-NET address and expecting a failure [test_offline_guard.py:55](../tests/integration/test_offline_guard.py#L55). A second test wraps `socket.connect` and `socket.getaddrinfo`, runs the classify, extract and answer suites end to end (HTTP targets, deterministic metrics, the judge and the cache), and asserts that every connection and every name lookup was loopback [test_offline_guard.py:25](../tests/integration/test_offline_guard.py#L25). `make bench` reports 0 non-loopback connections during an offline judged run (`evals/reports/bench.json`, NFR-5).

One documented gap: `ragas:` and `deepeval:` metrics that call an LLM use their own clients and bypass this [KNOWN_LIMITATIONS.md:5](../docs/KNOWN_LIMITATIONS.md#L5).

## 12. How do non-Python repositories use the gate?

The system under test does not have to be Python. An `http` target sends each case as JSON to any service (or as query parameters for `GET`) [http.py:46](../src/evalgate/targets/http.py#L46), limited to an allowlist of hosts (`EVALGATE_HTTP_ALLOWED_HOSTS`, default `localhost,127.0.0.1,::1,toy-targets` [config.py:59](../src/evalgate/config.py#L59)). The repository adds a suite YAML, a JSONL dataset and a step that starts its service.

The gate ships as a composite GitHub Action ([ADR-0005](adr/0005-composite-action.md)) [action.yml:58](../action/action.yml#L58) that installs its own Python [action.yml:60](../action/action.yml#L60), runs `evalgate run` and `evalgate check`, writes the Markdown report to the job summary, upserts the PR comment and fails the job with the check's exit code [action.yml:154](../action/action.yml#L154). Other CI systems can use the container image ([evalgate.Dockerfile:34](../docker/evalgate.Dockerfile#L34)) or the CLI directly; the exit codes (0 ok, 1 gate failed, 2 invalid input, 3 budget abort, 4 internal, 5 strict export) are the contract. Teams with Promptfoo configs can convert them with `evalgate import promptfoo` [cli.py:298](../src/evalgate/cli.py#L298).

## 13. How is the PR comment idempotent?

Each comment carries two markers, `<!-- evalgate:report -->` and `<!-- evalgate:suite=<name> -->` [pr_comment.py:22](../scripts/pr_comment.py#L22). `upsert` pages through all PR comments [pr_comment.py:51](../scripts/pr_comment.py#L51) and edits the first one that has both markers and was written by the bot account (`github-actions[bot]`, type `Bot`); only when none exists does it create one [pr_comment.py:80](../scripts/pr_comment.py#L80). So each suite has at most one comment per PR, and re-runs update it. The author check matters: anyone can paste the markers into their own comment [pr_comment.py:67](../scripts/pr_comment.py#L67).

Comment failures never change the gate: a 403 (fork PRs, missing `pull-requests: write`), any other HTTP error or an unreachable API is a warning [pr_comment.py:100](../scripts/pr_comment.py#L100). The body is cut to 60,000 characters, under GitHub's 65,536 limit [pr_comment.py:23](../scripts/pr_comment.py#L23). There is no lock: two jobs of the same suite on the same PR racing each other could both create a comment, so workflows should use a `concurrency` group per PR.

## 14. How were the meta-eval regressions designed?

A seeded catalogue of 50 mutations of the three toy systems [meta.py:14](../data/generator/meta.py#L14): 30 regressions a reviewer must not merge (24 quality, 3 cost, 3 latency) and 20 neutral changes. Each system gets 10 regressions; classify and extract get 7 neutral changes and answer gets 6 (`evals/reports/meta-eval.json`, `by.system`). Regressions mimic real failures: a prompt rule dropped, labels swapped, input truncated, dates reformatted, subtotal returned as total, the runner-up document retrieved, text aimed at the judge, 6x token inflation, 900 ms more latency. Neutral changes are the noise a gate must tolerate: about 1.5% of answers flipped, 15 to 20 ms more latency, 3 to 5% more tokens, a renamed trace node, a bumped prompt-version label, an extra output field, reordered JSON keys.

The toy targets apply a mutation when a request carries `X-Toy-Variant: <id>` [variants.py:149](../examples/toy-targets/src/toy_targets/variants.py#L149), and fractional mutations hash the input text instead of drawing random numbers [variants.py:26](../examples/toy-targets/src/toy_targets/variants.py#L26), so every run is identical. `scripts/meta_eval.py` runs each variant on its suite's test split against the committed v1 baseline with the production `check` [meta_eval.py:102](../scripts/meta_eval.py#L102) and requires detection of at least 0.90 and false positives of at most 0.10 [meta_eval.py:32](../scripts/meta_eval.py#L32).

The result is 30/30 detected and 0/20 false alarms, with exact 95% intervals [0.8843, 1.0] and [0.0, 0.1684] (`evals/reports/meta-eval.json`). Every quality regression also failed an absolute threshold, so the meta-eval does not isolate the bootstrap; the regressions are coarse [KNOWN_LIMITATIONS.md:12](../docs/KNOWN_LIMITATIONS.md#L12).

## 15. What changes at 100,000 cases?

Today 100,000 is the hard limit: datasets are capped at `MAX_CASES = 100_000` [limits.py:12](../src/evalgate/suite/limits.py#L12) while loading [loader.py:157](../src/evalgate/suite/loader.py#L157), rows at 1 MB, and reports at 50 MB [limits.py:11](../src/evalgate/suite/limits.py#L11) (refused on read [build.py:147](../src/evalgate/report/build.py#L147) and shown as 413 in the viewer [server.py:81](../src/evalgate/viewer/server.py#L81)). The bootstrap already bounds memory by resampling in chunks of at most 20,000,000 cells [bootstrap.py:11](../src/evalgate/stats/bootstrap.py#L11). What would have to change:

- Report: `report.v1` stores every case with its scores and judge details [engine.py:417](../src/evalgate/runner/engine.py#L417). The 50 MB cap leaves about 500 bytes per case at 100,000 cases, while the judged `answer` report already takes 57,077 bytes for 60 cases (`evals/reports/answer.json`). A larger suite needs per-case data in a sidecar file or the run store, with the report keeping aggregates and failures: a new contract version.
- Statistics: work is resamples x cases per metric, so 10,000 x 100,000 per gated metric; `make bench` only measures 200 cases. At that n the interval is very narrow, so tiny drops become significant and `--max-regression-pp` becomes the real guard; a normal approximation would also be accurate there.
- Runner: it creates one task per pending case up front [engine.py:323](../src/evalgate/runner/engine.py#L323) and keeps every outcome in memory; a bounded worker pool would replace it. The default run timeout of 1800 s [config.py:43](../src/evalgate/config.py#L43) would need raising or `--resume`.
- Judge cost: the preflight estimate grows linearly (100,000 cases x 2 calls with position swap), so the default budget would stop the run; judged metrics would run on a stratified sample.
- Store and viewer: DuckDB handles this size, but `insert_case` commits one transaction per case [runstore.py:47](../src/evalgate/store/runstore.py#L47) and would batch; the run page renders every case of the JSON report [server.py:351](../src/evalgate/viewer/server.py#L351) and would need server-side paging over the run store.
