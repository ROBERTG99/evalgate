-- 001_init: judge (and optional target) responses keyed by cassette key.
CREATE TABLE IF NOT EXISTS responses (
    key VARCHAR PRIMARY KEY,
    route VARCHAR NOT NULL,
    model VARCHAR,
    prompt_version VARCHAR,
    request_digest VARCHAR,
    response JSON NOT NULL,
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    cost_usd DOUBLE NOT NULL DEFAULT 0,
    latency_ms DOUBLE NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL,
    hits INTEGER NOT NULL DEFAULT 0
);
