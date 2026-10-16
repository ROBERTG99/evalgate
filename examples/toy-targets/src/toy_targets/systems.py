"""Deterministic toy AI systems: rule-based stand-ins for a classifier, an extractor and a RAG agent.

They never call a model. Token counts are synthetic (derived from text length) and priced as
``toy-model``. ``v1`` is the good version; ``v2`` is a plausible prompt change that regresses.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import re
from functools import cache
from pathlib import Path
from typing import Any

MODEL = "toy-model"

CLASSIFY_RULES: list[tuple[str, list[str]]] = [
    ("account_access", ["log in", "login", "password", "locked out", "two-factor", "sign in"]),
    ("cancellation", ["cancel", "close my account", "unsubscribe", "terminate"]),
    ("feature_request", ["would be great", "could you add", "suggestion", "please add", "i wish", "dark mode"]),
    ("billing", ["charged", "refund", "payment", "invoice", "receipt", "billing", "fee"]),
    ("shipping", ["arrived", "tracking", "courier", "parcel", "shipped", "delivery"]),
    ("bug_report", ["crash", "error", "freezes", "broken", "bug", "fails", "not working"]),
]
DEFAULT_LABEL = "bug_report"
PROMPT_TOKENS = {"classify": 120, "extract": 150, "answer": 260}


def tokens_for(text: str, base: int) -> int:
    return base + max(1, len(text) // 4)


def llm_step(node: str, prompt_version: str, prompt_text: str, output_text: str, base: int) -> dict[str, Any]:
    return {
        "node": node,
        "kind": "llm",
        "model": MODEL,
        "prompt_version": prompt_version,
        "input_tokens": tokens_for(prompt_text, base),
        "output_tokens": max(1, len(output_text) // 4),
        "status": "ok",
    }


# classify ----------------------------------------------------------------------------------------
def classify(
    text: str, version: str = "v1", drop: set[str] | None = None, truncate: int | None = None
) -> dict[str, Any]:
    rules = CLASSIFY_RULES
    if version == "v2":  # "shorter prompt": the account-access instructions were cut
        rules = [r for r in rules if r[0] != "account_access"]
    if drop:
        rules = [r for r in rules if r[0] not in drop]
    seen = (text[:truncate] if truncate else text).lower()
    label, hits = DEFAULT_LABEL, 0
    for name, keywords in rules:
        n = sum(1 for k in keywords if k in seen)
        if n:
            label, hits = name, n
            break
    confidence = round(min(0.98, 0.55 + 0.15 * hits), 2)
    step = llm_step("classify", f"toy_classify.{version}", text, label, PROMPT_TOKENS["classify"])
    return {"label": label, "confidence": confidence, "steps": [step]}


# extract -----------------------------------------------------------------------------------------
SYMBOLS = {"€": "EUR", "$": "USD", "£": "GBP"}
MONEY = re.compile(r"([€$£])?\s?(\d{1,3}(?:,\d{3})*\.\d{2})\s?(EUR|USD|GBP)?")
TOTAL_LINE = re.compile(r"^(total due|total|amount due|balance due|grand total)\b", re.IGNORECASE)
DATE_FORMATS = ["%Y-%m-%d", "%d %b %Y", "%B %d, %Y"]


def _money(line: str) -> tuple[float, str | None] | None:
    m = MONEY.search(line)
    if not m:
        return None
    currency = m.group(3) or SYMBOLS.get(m.group(1) or "")
    return float(m.group(2).replace(",", "")), currency


def _date(text: str) -> str | None:
    for fmt in DATE_FORMATS:
        try:
            return dt.datetime.strptime(text.strip(), fmt).date().isoformat()
        except ValueError:
            continue
    return None


def extract(document: str, version: str = "v1") -> dict[str, Any]:
    lines = [ln.strip() for ln in document.splitlines() if ln.strip()]
    vendor = lines[0] if lines else ""
    number = re.search(r"INV-\d{5}", document)
    date_iso: str | None = None
    total: float | None = None
    currency: str | None = None
    subtotal: float | None = None
    for line in lines:
        if line.lower().startswith("date:"):
            date_iso = _date(line[5:])
        if line.lower().startswith("subtotal"):
            parsed = _money(line)
            subtotal = parsed[0] if parsed else None
        elif total is None and TOTAL_LINE.match(line):
            parsed = _money(line)
            if parsed:
                total, currency = parsed
    if total is None:  # fall back to the last amount in the document
        amounts = [p for p in (_money(ln) for ln in lines) if p]
        if amounts:
            total, currency = amounts[-1]
    if version == "v2" and date_iso:  # "locale-aware" prompt change: dates in DD/MM/YYYY
        d = dt.date.fromisoformat(date_iso)
        date_iso = d.strftime("%d/%m/%Y")
    out = {
        "invoice_number": number.group(0) if number else "",
        "date": date_iso or "",
        "total": total if total is not None else 0.0,
        "currency": currency or "",
        "vendor": vendor,
    }
    step = llm_step("extract_fields", f"toy_extract.{version}", document, json.dumps(out), PROMPT_TOKENS["extract"])
    return {**out, "steps": [step], "_subtotal": subtotal}


# answer ------------------------------------------------------------------------------------------
STOP = {
    "what",
    "when",
    "with",
    "your",
    "have",
    "does",
    "from",
    "that",
    "this",
    "there",
    "which",
    "about",
    "into",
    "will",
    "much",
    "many",
    "long",
    "after",
    "before",
    "quick",
    "question",
    "hello",
    "should",
    "until",
    "time",
    "must",
    "make",
    "need",
    "page",
    "explains",
    "bought",
    "the",
    "and",
    "for",
    "are",
    "how",
    "can",
    "our",
    "you",
}
SENTENCE = re.compile(r"(?<=[.!?])\s+")


def stem(word: str) -> str:
    for suffix in ("ing", "ed", "es", "s"):
        if len(word) > 4 + len(suffix) - 1 and word.endswith(suffix):
            return word[: -len(suffix)]
    return word


def words(text: str) -> set[str]:
    return {stem(w) for w in re.findall(r"[a-z0-9:%€]+", text.lower()) if len(w) > 2 and w not in STOP}


def data_dir() -> Path:
    env = os.environ.get("TOY_DATA_DIR")
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[4] / "evals" / "datasets"


@cache
def corpus() -> dict[str, dict[str, str]]:
    path = data_dir() / "toys" / "faq_corpus.v1.jsonl"
    docs = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        docs[row["id"]] = {"title": row["input"]["title"], "text": row["input"]["text"]}
    return docs


def search_faq(query: str, k: int = 3) -> list[tuple[str, int]]:
    q = words(query)
    scored = [(doc_id, len(q & words(doc["title"] + " " + doc["text"]))) for doc_id, doc in corpus().items()]
    scored.sort(key=lambda x: (-x[1], x[0]))
    return scored[:k]


def read_doc(doc_id: str, max_chars: int = 500) -> str:
    return corpus().get(doc_id, {"text": ""})["text"][:max_chars]


def best_sentence(question: str, text: str) -> str:
    sentences = SENTENCE.split(text)
    body = sentences[1:-1] or sentences  # skip the intro and the contact line
    q = words(question)
    return max(body, key=lambda s: (len(q & words(s)), -body.index(s)))


def answer(question: str, version: str = "v1", options: dict[str, Any] | None = None) -> dict[str, Any]:
    opts = options or {}
    hits = search_faq(question)
    doc_id = hits[1][0] if opts.get("second_best_doc") and len(hits) > 1 else hits[0][0]
    steps: list[dict[str, Any]] = [
        {"node": "search_faq", "kind": "tool", "args": {"query": question, "k": 3}, "status": "ok"}
    ]
    if opts.get("skip_read_doc"):
        text = corpus()[doc_id]["text"][:160]
    else:
        read_id = opts.get("read_doc_id_override") or doc_id
        steps.append(
            {"node": "read_doc", "kind": "tool", "args": {"doc_id": read_id, "max_chars": 500}, "status": "ok"}
        )
        text = read_doc(doc_id)
    if opts.get("first_sentence"):
        reply = SENTENCE.split(text)[0]
    else:
        reply = best_sentence(question, text)
    if version == "v2":  # "be brief" prompt change: answers capped at 70 characters
        reply = reply if len(reply) <= 70 else reply[:70].rsplit(" ", 1)[0] + "…"
    steps.append(llm_step("generate", f"toy_answer.{version}", question + text, reply, PROMPT_TOKENS["answer"]))
    return {"answer": reply, "citations": [doc_id], "steps": steps}
