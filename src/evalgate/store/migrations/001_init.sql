-- 001_init: runs, case results, metric scores, steps and the gate audit chain.
CREATE TABLE IF NOT EXISTS runs (
    run_id VARCHAR PRIMARY KEY,
    suite VARCHAR NOT NULL,
    split VARCHAR CHECK (split IN ('dev', 'test')),
    created_at TIMESTAMP NOT NULL,
    git_sha VARCHAR,
    mode VARCHAR NOT NULL CHECK (mode IN ('offline', 'live')),
    n_cases INTEGER NOT NULL,
    passed BOOLEAN NOT NULL,
    cost_usd_total DOUBLE NOT NULL,
    latency_p50_ms DOUBLE NOT NULL,
    latency_p95_ms DOUBLE NOT NULL,
    report_path VARCHAR,
    report_sha256 VARCHAR
);
CREATE INDEX IF NOT EXISTS runs_suite_created ON runs (suite, created_at);

CREATE TABLE IF NOT EXISTS case_results (
    run_id VARCHAR NOT NULL,
    case_id VARCHAR NOT NULL,
    split VARCHAR CHECK (split IN ('dev', 'test')),
    passed BOOLEAN NOT NULL,
    cost_usd DOUBLE NOT NULL,
    latency_ms DOUBLE NOT NULL,
    attempts INTEGER NOT NULL,
    error VARCHAR,
    PRIMARY KEY (run_id, case_id)
);

CREATE TABLE IF NOT EXISTS metric_scores (
    run_id VARCHAR NOT NULL,
    case_id VARCHAR NOT NULL,
    metric VARCHAR NOT NULL,
    value DOUBLE NOT NULL,
    passed BOOLEAN NOT NULL,
    details JSON,
    PRIMARY KEY (run_id, case_id, metric)
);

CREATE TABLE IF NOT EXISTS steps (
    run_id VARCHAR NOT NULL,
    case_id VARCHAR NOT NULL,
    step INTEGER NOT NULL,
    task_id VARCHAR,
    node VARCHAR NOT NULL,
    kind VARCHAR NOT NULL CHECK (kind IN ('llm', 'tool', 'retrieval', 'judge', 'target', 'other')),
    model VARCHAR,
    prompt_version VARCHAR,
    input_tokens INTEGER NOT NULL,
    output_tokens INTEGER NOT NULL,
    cost_usd DOUBLE NOT NULL,
    latency_ms DOUBLE NOT NULL,
    status VARCHAR NOT NULL CHECK (status IN ('ok', 'error', 'timeout', 'skipped')),
    error VARCHAR,
    started_at TIMESTAMP,
    PRIMARY KEY (run_id, case_id, step)
);

CREATE TABLE IF NOT EXISTS gate_audit (
    seq BIGINT PRIMARY KEY,
    ts TIMESTAMP NOT NULL,
    report_sha256 VARCHAR NOT NULL,
    baseline_sha256 VARCHAR,
    git_sha VARCHAR,
    decision VARCHAR NOT NULL CHECK (decision IN ('pass', 'fail')),
    failures JSON,
    actor VARCHAR,
    prev_hash VARCHAR NOT NULL,
    hash VARCHAR NOT NULL
);
