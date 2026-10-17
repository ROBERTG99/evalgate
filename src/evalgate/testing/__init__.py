"""Testing helpers for evalgate users: cassettes, a rule-based judge and an offline LLM (FR-13).

``Cassette`` is the recorded-response contract (``schemas/cassette.v1.json``) plus key helpers,
``FakeJudge`` scores rendered judge prompts with deterministic rules, and ``FakeLLM`` is the offline
provider: it replays a matching cassette, raises :class:`CassetteMismatch` for a stale one, and
otherwise answers with ``FakeJudge``.
"""

from evalgate.contracts import Cassette
from evalgate.errors import CassetteMismatch, CassetteMismatchError
from evalgate.judge.fake import FakeJudge
from evalgate.llm.cassette import cassette_key, load, request_digest, request_key, save
from evalgate.llm.fake import FakeLLM

__all__ = [
    "Cassette",
    "CassetteMismatch",
    "CassetteMismatchError",
    "FakeJudge",
    "FakeLLM",
    "cassette_key",
    "load",
    "request_digest",
    "request_key",
    "save",
]
