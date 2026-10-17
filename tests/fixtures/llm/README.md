# LLM cassettes

Recorded judge responses live here as `<route>/<key>.json` (`schemas/cassette.v1.json`), keyed by
`sha256(route | model | prompt_version | canonical_json(messages, schema_name))`. FakeLLM replays a
cassette when one matches a request and raises `CassetteMismatch` when the stored `request_digest`
differs (prompt, schema, effort or limits changed); without a cassette it answers with FakeJudge rules.

Cassettes are written by `make record-fixtures` (a live run with `EVALGATE_RECORD_CASSETTES=1`). None
are committed yet because no provider key was available during the build (see
`docs/KNOWN_LIMITATIONS.md`). Provider adapters are tested against response fixtures in the documented
API shapes in `tests/fixtures/provider_responses/`.
