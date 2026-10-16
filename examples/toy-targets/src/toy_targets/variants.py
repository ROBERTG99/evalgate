"""Apply the catalogued mutations (``evals/datasets/meta/variants.v1.jsonl``) to the toy systems."""

from __future__ import annotations

import copy
import datetime as dt
import hashlib
import json
import re
from functools import cache
from typing import Any

from toy_targets import systems


@cache
def catalogue() -> dict[str, dict[str, Any]]:
    path = systems.data_dir() / "meta" / "variants.v1.jsonl"
    out = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        out[row["id"]] = {"system": row["input"]["system"], **row["meta"]}
    return out


def _fraction(key: str) -> float:
    """A deterministic number in [0, 1) per input text."""
    return int(hashlib.sha256(key.encode()).hexdigest()[:8], 16) / 2**32


def _scale_tokens(out: dict[str, Any], factor: float) -> None:
    for step in out.get("steps", []):
        if step.get("kind") == "llm":
            step["input_tokens"] = round(step["input_tokens"] * factor)
            step["output_tokens"] = round(step["output_tokens"] * factor)


def _rename_step(out: dict[str, Any], node: str) -> None:
    for step in out.get("steps", []):
        if step.get("kind") == "llm":
            step["node"] = node


def _prompt_version(out: dict[str, Any], value: str) -> None:
    for step in out.get("steps", []):
        if step.get("kind") == "llm":
            step["prompt_version"] = value


def classify(text: str, variant: dict[str, Any]) -> dict[str, Any]:
    m, p = variant["mutation"], variant["params"]
    if m == "drop_rule":
        return systems.classify(text, drop={p["label"]})
    if m == "truncate_input":
        return systems.classify(text, truncate=int(p["chars"]))
    out = systems.classify(text)
    if m == "swap_labels":
        swap = {p["a"]: p["b"], p["b"]: p["a"]}
        out["label"] = swap.get(out["label"], out["label"])
    elif m == "default_bias" and _fraction(text) < float(p["rate"]):
        out["label"] = systems.DEFAULT_LABEL
    elif m == "uppercase_label":
        out["label"] = out["label"].capitalize()
    elif m == "confidence_jitter":
        out["confidence"] = round(
            min(0.99, max(0.01, out["confidence"] + (_fraction(text) - 0.5) * 2 * p["amount"])), 2
        )
    elif m == "flip_fraction" and _fraction("flip:" + text) < float(p["rate"]):
        labels = [r[0] for r in systems.CLASSIFY_RULES]
        out["label"] = labels[(labels.index(out["label"]) + 1) % len(labels)] if out["label"] in labels else labels[0]
    elif m == "add_output_field":
        out[p["field"]] = "matched keywords for the label"
    _common(out, m, p)
    return out


def extract(document: str, variant: dict[str, Any]) -> dict[str, Any]:
    m, p = variant["mutation"], variant["params"]
    out = systems.extract(document)
    if m == "drop_field":
        out.pop(p["field"], None)
    elif m == "date_format" and out["date"]:
        out["date"] = dt.date.fromisoformat(out["date"]).strftime(p["format"])
    elif m == "round_total":
        out["total"] = float(round(out["total"]))
    elif m == "lowercase_currency":
        out["currency"] = out["currency"].lower()
    elif m == "use_subtotal" and out.get("_subtotal") is not None:
        out["total"] = out["_subtotal"]
    elif m == "strip_invoice_prefix":
        out["invoice_number"] = out["invoice_number"].removeprefix("INV-")
    elif m == "total_as_string":
        out["total"] = f"{out['total']:.2f}"
    elif m == "swap_day_month" and out["date"]:
        d = dt.date.fromisoformat(out["date"])
        if d.day <= 12:
            out["date"] = dt.date(d.year, d.day, d.month).isoformat()
    elif m == "flip_fraction" and _fraction("flip:" + document) < float(p["rate"]):
        out["total"] = round(out["total"] + 1.0, 2)
    elif m == "add_output_field":
        out[p["field"]] = 0.97
    elif m == "reorder_keys":
        out = dict(reversed(list(out.items())))
    _common(out, m, p)
    return out


def answer(question: str, variant: dict[str, Any]) -> dict[str, Any]:
    m, p = variant["mutation"], variant["params"]
    options: dict[str, Any] = {}
    if m in ("second_best_doc", "skip_read_doc", "first_sentence"):
        options[m] = True
    if m == "wrong_doc_arg":
        right = systems.search_faq(question)[0][0]
        number = int(right.split("-")[1])
        options["read_doc_id_override"] = f"faq-{number % 40 + 1:02d}"
    out = systems.answer(question, options=options)
    if m == "drop_numbers":
        out["answer"] = re.sub(r"\s{2,}", " ", re.sub(r"[€$£]?\d+(?:[.,:]\d+)*", "", out["answer"]))
    elif m == "off_by_one":
        out["answer"] = re.sub(r"\d+", lambda x: str(int(x.group(0)) + 1), out["answer"])
    elif m in ("inject_text", "polite_suffix"):
        out["answer"] = f"{out['answer']} {p['text']}"
    elif m == "answer_prefix":
        out["answer"] = p["text"] + out["answer"][0].lower() + out["answer"][1:]
    elif m == "truncate_answer":
        out["answer"] = out["answer"][: int(p["chars"])]
    elif m == "reverse_citations":
        out["citations"] = list(reversed(out["citations"] + [systems.search_faq(question)[1][0]]))
    _common(out, m, p)
    return out


def _common(out: dict[str, Any], mutation: str, params: dict[str, Any]) -> None:
    if mutation == "token_inflation":
        _scale_tokens(out, float(params["factor"]))
    elif mutation == "rename_step":
        _rename_step(out, params["node"])
    elif mutation == "prompt_version":
        _prompt_version(out, params["value"])


def latency_ms(variant: dict[str, Any] | None) -> float:
    if variant and variant["mutation"] == "latency_ms":
        return float(variant["params"]["ms"])
    return 0.0


def apply(system: str, payload: str, variant: dict[str, Any]) -> dict[str, Any]:
    fn = {"classify": classify, "extract": extract, "answer": answer}[system]
    return copy.deepcopy(fn(payload, variant))
