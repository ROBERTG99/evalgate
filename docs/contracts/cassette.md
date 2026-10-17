# Cassette contract: `cassette.v1`

## Purpose

A cassette is one recorded provider response, stored as a JSON file so that judged runs and tests replay real model output offline. `FakeLLM` replays a cassette when one matches a request, raises `CassetteMismatch` when the stored request digest differs, and otherwise answers with the FakeJudge rules. Live runs write cassettes when `EVALGATE_RECORD_CASSETTES=1` (`make record-fixtures`). The response cache (`cache.duckdb`) uses the same key function for its rows.

- JSON Schema: [schemas/cassette.v1.json](../../schemas/cassette.v1.json) (also `evalgate schema cassette`).
- Source of truth: `Cassette` and `CassetteUsage` in [src/evalgate/contracts/judge.py](../../src/evalgate/contracts/judge.py).
- Keying, loading and saving: [src/evalgate/llm/cassette.py](../../src/evalgate/llm/cassette.py). Recording happens only in the gateway ([src/evalgate/llm/gateway.py](../../src/evalgate/llm/gateway.py), [ADR-0002](../adr/0002-thin-provider-gateway.md)).

## Location and key

- Path: `<EVALGATE_CASSETTE_DIR>/<route>/<key>.json`, with `EVALGATE_CASSETTE_DIR` defaulting to `tests/fixtures/llm`.
- `key = sha256(route | model | prompt_version | canonical_json([messages, schema_name]))`, where `|` is a literal separator and `canonical_json` sorts keys, uses no whitespace and keeps UTF-8 (`ensure_ascii=False`, [src/evalgate/ids.py](../../src/evalgate/ids.py)). For cassettes, messages are hashed after the gateway's PII redaction, because the gateway redacts before FakeLLM or a provider sees the request.
- `request_digest = sha256(canonical_json({route, model, prompt_version, system, messages, schema_name, schema, effort, max_tokens}))`. The key finds the cassette; the digest proves that everything else that shapes the response (system prompt, schema, effort, limits) is unchanged.

## Fields

### Cassette

| Name | Type | Required | Meaning |
|---|---|---|---|
| `key` | string, 64 lowercase hex characters | yes | The cassette key above; also the file name. |
| `route` | string | yes | Model route, `judge` or `judge_hard`; also the folder name. |
| `model` | string | yes | Model ID the request was sent to. |
| `prompt_version` | string | yes | Prompt file name without `.md`, for example `judge_answer_correctness.v1`. |
| `request_digest` | string, 64 lowercase hex characters | yes | Digest of the full request (above). |
| `response` | object | yes | The parsed JSON the provider returned; for judges, a `judge_verdict.v1` object. |
| `usage` | object (Usage) | yes | Token counts of the recorded call. |
| `recorded_at` | string | yes | UTC timestamp, ISO 8601 with `Z`, seconds precision. |

### Usage

| Name | Type | Required | Meaning |
|---|---|---|---|
| `input_tokens` | integer at least 0 | yes | Input tokens reported by the provider. |
| `output_tokens` | integer at least 0 | yes | Output tokens reported by the provider. |

## Minimal valid example

No cassette is committed yet ([tests/fixtures/llm/README.md](../../tests/fixtures/llm/README.md)). The example below was built for this page: `key` and `request_digest` were computed with `request_key` and `request_digest` from [src/evalgate/llm/cassette.py](../../src/evalgate/llm/cassette.py) for the `answer_correctness.v1` rubric, model `claude-haiku-5-5`, and a rendered message for the input "How long are gift cards valid?", reference "Gift cards are valid for 2 years." and candidate "They are valid for 2 years." (reference first). The token counts and the timestamp are illustrative, not from a recorded call.

```json
{
  "key": "fcaac888d2bad872730c2793d7b0028c5cc6a1f806430c8bd99e65292ca55a74",
  "model": "claude-haiku-5-5",
  "prompt_version": "judge_answer_correctness.v1",
  "recorded_at": "2026-10-16T12:00:00Z",
  "request_digest": "bc87356a15f8170ed4a2f9b3fe88c2aacefc94eee7bddda034a0e9c20ab0aca5",
  "response": {
    "criteria": {"answers_question": "met", "no_contradiction": "met", "states_key_facts": "met"},
    "reasons": ["states the 2-year validity"],
    "score": 1,
    "verdict": "pass"
  },
  "route": "judge",
  "usage": {"input_tokens": 900, "output_tokens": 60}
}
```

It would be stored as `tests/fixtures/llm/judge/fcaac888d2bad872730c2793d7b0028c5cc6a1f806430c8bd99e65292ca55a74.json`. `save` writes cassettes with sorted keys and two-space indentation.

## Versioning

- The Pydantic models are the source of truth. `uv run python scripts/export_schemas.py` (or `make docs`) regenerates `schemas/`; `make schemas` runs the export with `--check` and fails on drift, as does `tests/contract/test_schemas.py::test_no_drift`.
- Additive changes keep `v1`: a new optional field with a default.
- Breaking changes create `cassette.v2` with its own schema file, and so does any change to how `key` or `request_digest` is computed, because it orphans every recorded cassette.

## Compatibility notes

- A cassette whose `request_digest` no longer matches raises `CassetteMismatch` instead of replaying a stale answer; re-record with `make record-fixtures`.
- Changing the prompt file version, the model ID or the route changes the key, so the old cassette is simply not found and the request falls through to FakeJudge (offline) or the provider (live).
- The response cache uses the same key and also stores the digest; a cache row whose `request_digest` differs is treated as stale.
- Cassettes are committed fixtures: they must never contain secrets or real personal data.
