"""FakeJudge: a deterministic, rule-based judge used offline and in tests.

Pointwise binary: pass when the candidate contains every key fact of the reference (numbers, times,
amounts, percentages, dates and capitalised entities) and no number the reference does not contain;
references without such facts need 60% recall of their content words. Pairwise: prefers the candidate
with more reference facts net of contradictions, else ``tie``. Likert5 (rubric adherence): one point per
met criterion. Phrases in ``injection_patterns.yaml`` force ``fail``.
"""

from __future__ import annotations

import re
from typing import Any

from evalgate.judge.guard import injection_match
from evalgate.judge.render import parse_user

NUMBER = re.compile(r"\d+(?:[.,:]\d+)*")
ENTITY = re.compile(r"(?<![.!?]\s)(?<!^)\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+\b")
STOP = {
    "the",
    "and",
    "for",
    "are",
    "our",
    "with",
    "within",
    "from",
    "this",
    "that",
    "your",
    "you",
    "can",
    "all",
    "will",
    "has",
    "have",
    "into",
    "about",
    "after",
    "than",
    "then",
    "they",
    "them",
    "their",
    "any",
}
CITATION = re.compile(r"\[faq-\d+\]")
MAX_CONCISE_WORDS = 60


def numbers(text: str) -> set[str]:
    return {n.replace(",", "") for n in NUMBER.findall(text)}


def entities(text: str) -> set[str]:
    return set(ENTITY.findall(text))


def content_words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]+", text.lower()) if len(w) > 3 and w not in STOP}


def fact_check(reference: str, candidate: str) -> tuple[int, int, int, list[str]]:
    """Return (facts present, facts total, contradictions, missing)."""
    ref_nums, cand_nums = numbers(reference), numbers(candidate)
    ref_ents = entities(reference)
    facts = sorted(ref_nums) + sorted(ref_ents)
    present = [f for f in facts if (f in cand_nums if f in ref_nums else f in candidate)]
    contradictions = len(cand_nums - ref_nums)
    missing = [f for f in facts if f not in present]
    if not facts:
        ref_words = content_words(reference)
        if ref_words:
            recall = len(ref_words & content_words(candidate)) / len(ref_words)
            ok = recall >= 0.6
            return (1 if ok else 0), 1, contradictions, [] if ok else ["content"]
    return len(present), len(facts), contradictions, missing


def _criteria(names: list[str], met: dict[str, bool]) -> dict[str, str]:
    return {n: "met" if met.get(n, True) else "unmet" for n in names}


def judge_pointwise(parsed: dict[str, Any]) -> dict[str, Any]:
    candidate = parsed["candidates"].get("_", "")
    reference = parsed.get("reference", "")
    names = parsed.get("criteria", [])
    hit = injection_match(candidate)
    if hit:
        return {
            "verdict": "fail",
            "score": 0.0,
            "reasons": [f"instruction aimed at the grader: {hit!r}"],
            "criteria": _criteria(names, dict.fromkeys(names, False)),
        }
    present, total, contradictions, missing = fact_check(reference, candidate)
    facts_ok = present == total
    no_contradiction = contradictions == 0
    if parsed.get("scale") == "likert5":
        met = {
            "cites_source": bool(CITATION.search(candidate)),
            "states_key_facts": facts_ok and no_contradiction,
            "concise": len(candidate.split()) <= MAX_CONCISE_WORDS,
        }
        relevant = [n for n in names if n in met] or list(met)
        n_met = sum(met[n] for n in relevant)
        score = n_met / len(relevant)
        reasons = [f"{n} unmet" for n in relevant if not met[n]][:3] or ["all criteria met"]
        return {
            "verdict": "pass" if n_met == len(relevant) else "fail",
            "score": round(score, 4),
            "reasons": reasons,
            "criteria": _criteria(names, met),
        }
    passed = facts_ok and no_contradiction
    reasons = []
    if missing:
        reasons.append("missing key facts: " + ", ".join(missing[:5]))
    if not no_contradiction:
        reasons.append(f"{contradictions} number(s) not in the reference")
    met = {"states_key_facts": facts_ok, "no_contradiction": no_contradiction, "answers_question": passed}
    return {
        "verdict": "pass" if passed else "fail",
        "score": 1.0 if passed else 0.0,
        "reasons": reasons[:3] or ["all key facts present"],
        "criteria": _criteria(names, met),
    }


def judge_pairwise(parsed: dict[str, Any]) -> dict[str, Any]:
    reference = parsed.get("reference", "")
    names = parsed.get("criteria", [])
    scores = {}
    for ident in ("A", "B"):
        cand = parsed["candidates"].get(ident, "")
        if injection_match(cand):
            scores[ident] = -1_000
            continue
        present, _total, contradictions, _ = fact_check(reference, cand)
        scores[ident] = present - contradictions
    if scores["A"] == scores["B"]:
        return {"verdict": "tie", "score": 0.5, "reasons": ["equal reference facts"], "criteria": _criteria(names, {})}
    winner = "A" if scores["A"] > scores["B"] else "B"
    return {
        "verdict": winner,
        "score": 1.0,
        "reasons": [f"{winner} states more reference facts"],
        "criteria": _criteria(names, {}),
    }


class FakeJudge:
    """Rule-based judge over a rendered judge prompt (see :mod:`evalgate.judge.render`)."""

    def verdict(self, user_message: str) -> dict[str, Any]:
        parsed = parse_user(user_message)
        if parsed.get("mode") == "pairwise":
            return judge_pairwise(parsed)
        return judge_pointwise(parsed)

    def usage(self, user_message: str, response: dict[str, Any]) -> tuple[int, int]:
        """Synthetic token counts (characters / 4), as a real provider would report."""
        return max(1, len(user_message) // 4), max(1, len(str(response)) // 4)
