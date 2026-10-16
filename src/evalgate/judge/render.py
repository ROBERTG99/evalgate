"""Judge prompt rendering with candidate isolation.

Instructions live in the system prompt (``prompts/judge_<rubric>.v<N>.md``). Task input, reference and
candidates appear only in the user message, HTML-escaped inside ``<task_input>``, ``<reference>`` and
``<candidate_output>`` tags, so a candidate cannot close a tag or pose as an instruction.
"""

from __future__ import annotations

import html
import re
from typing import Any

from evalgate.contracts import Rubric

TAG = re.compile(r"<(task_input|reference|candidate_output)(?: id=\"([AB])\")?>(.*?)</\1>", re.S)
RUBRIC_TAG = re.compile(r'<rubric name="([a-z0-9_]+)" version="(\d+)" mode="(\w+)" scale="(\w+)">')


def esc(text: str) -> str:
    return html.escape(text, quote=False)


def render_user(
    rubric: Rubric,
    *,
    task_input: str,
    reference: str,
    candidate: str,
    candidate_b: str | None = None,
    order: str = "reference_first",
) -> str:
    criteria = "\n".join(f"- {c}" for c in rubric.criteria)
    head = (
        f'<rubric name="{rubric.name}" version="{rubric.version}" mode="{rubric.mode}" scale="{rubric.scale}">\n'
        f"<criteria>\n{criteria}\n</criteria>\n</rubric>\n"
        f"<task_input>{esc(task_input)}</task_input>\n"
    )
    ref = f"<reference>{esc(reference)}</reference>\n"
    if rubric.mode == "pairwise":
        assert candidate_b is not None
        first, second = (candidate, candidate_b) if order == "AB" else (candidate_b, candidate)
        body = ref + (
            f'<candidate_output id="A">{esc(first)}</candidate_output>\n'
            f'<candidate_output id="B">{esc(second)}</candidate_output>\n'
        )
    else:
        cand = f"<candidate_output>{esc(candidate)}</candidate_output>\n"
        body = cand + ref if order == "candidate_first" else ref + cand
    return head + body + "Respond with one judge_verdict.v1 JSON object."


def parse_user(message: str) -> dict[str, Any]:
    """Inverse of :func:`render_user` (used by FakeJudge)."""
    out: dict[str, Any] = {"candidates": {}}
    m = RUBRIC_TAG.search(message)
    if m:
        out.update(rubric=m.group(1), version=int(m.group(2)), mode=m.group(3), scale=m.group(4))
    crit = re.search(r"<criteria>\n(.*?)\n</criteria>", message, re.S)
    out["criteria"] = [c[2:] for c in crit.group(1).splitlines()] if crit else []
    for tag, ident, text in TAG.findall(message):
        value = html.unescape(text)
        if tag == "candidate_output":
            out["candidates"][ident or "_"] = value
        else:
            out[tag] = value
    return out


def verdict_schema(rubric: Rubric) -> dict[str, Any]:
    """JSON schema sent as ``output_config.format``; criteria keys are the rubric's criteria."""
    verdicts = ["A", "B", "tie"] if rubric.mode == "pairwise" else ["pass", "fail"]
    return {
        "type": "object",
        "properties": {
            "verdict": {"type": "string", "enum": verdicts},
            "score": {"type": "number", "minimum": 0, "maximum": 1},
            "reasons": {"type": "array", "items": {"type": "string"}, "maxItems": 3},
            "criteria": {
                "type": "object",
                "properties": {c: {"type": "string", "enum": ["met", "unmet"]} for c in rubric.criteria},
                "required": list(rubric.criteria),
                "additionalProperties": False,
            },
        },
        "required": ["verdict", "score", "reasons", "criteria"],
        "additionalProperties": False,
    }
