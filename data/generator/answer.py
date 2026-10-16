"""Synthetic FAQ corpus (40 documents) and questions with reference answers and expected tool calls."""

from __future__ import annotations

import random
from typing import Any

from data.generator.common import rng, stratified_splits

COMPANY = "Pinecrest Supply"  # fictional
LINES = ["garden tools", "kitchenware"]

# (sentence, slots, key facts, questions). Slots are filled once per document.
Fact = tuple[str, dict[str, list[Any]], list[str], list[str]]
SCHEMAS: list[tuple[str, str, list[Fact]]] = [
    (
        "returns",
        "Returns for {line}",
        [
            (
                "Unused {line} can be returned within {n} days of delivery for a full refund.",
                {"n": [14, 30, 45]},
                ["{n} days"],
                [
                    "How many days do I have to return unused {line}?",
                    "Within how many days of delivery can unused {line} be returned?",
                ],
            ),
            (
                "Refunds for returned {line} reach the original payment method within {m} business days.",
                {"m": [3, 5, 7]},
                ["{m} business days"],
                ["How long do refunds for returned {line} take to reach my payment method?"],
            ),
        ],
    ),
    (
        "warranty",
        "Warranty on {line}",
        [
            (
                "All {line} carry a {y}-year warranty against manufacturing defects.",
                {"y": [2, 3, 5]},
                ["{y}-year"],
                ["How long is the warranty on {line}?", "What warranty do {line} carry against defects?"],
            ),
            (
                "Warranty claims for {line} need the order number and a photo of the defect.",
                {},
                ["order number", "photo"],
                ["What do I need to file a warranty claim for {line}?"],
            ),
        ],
    ),
    (
        "shipping_cost",
        "Shipping costs for {line}",
        [
            (
                "Standard shipping for {line} costs {fee} and is free on orders over {free}.",
                {"fee": ["€4.95", "€5.50", "€6.90"], "free": ["€50", "€60", "€75"]},
                ["{fee}", "{free}"],
                [
                    "How much does standard shipping cost for {line}?",
                    "What is the standard shipping fee for {line} orders?",
                ],
            ),
        ],
    ),
    (
        "delivery_time",
        "Delivery times for {line}",
        [
            (
                "Orders of {line} placed before {cut} ship the same business day.",
                {"cut": ["13:00", "14:00", "15:00"]},
                ["{cut}"],
                ["What is the same-day shipping cut-off time for {line} orders?"],
            ),
            (
                "Standard delivery of {line} takes {d} business days within the country.",
                {"d": [2, 3, 4]},
                ["{d} business days"],
                ["How many business days does standard delivery of {line} take?"],
            ),
        ],
    ),
    (
        "support_hours",
        "Support hours for {line}",
        [
            (
                "The {line} support team answers calls from {start} to {end} on weekdays.",
                {"start": ["08:00", "09:00"], "end": ["17:00", "18:00"]},
                ["{start}", "{end}"],
                ["What are the weekday phone support hours for {line}?"],
            ),
            (
                "On Saturdays the {line} support chat is open until {sat}.",
                {"sat": ["12:00", "14:00"]},
                ["{sat}"],
                ["Until what time is the {line} support chat open on Saturdays?"],
            ),
        ],
    ),
    (
        "price_match",
        "Price match for {line}",
        [
            (
                "We match the price of {line} sold by another shop for up to {pm} days after purchase.",
                {"pm": [7, 14]},
                ["{pm} days"],
                ["For how many days after purchase do you price match {line}?"],
            ),
        ],
    ),
    (
        "bulk",
        "Bulk orders of {line}",
        [
            (
                "Bulk orders of {line} with more than {q} units get a {pct}% discount.",
                {"q": [20, 50, 100], "pct": [5, 10, 15]},
                ["{q} units", "{pct}%"],
                [
                    "What discount do bulk orders of {line} get?",
                    "How many units make a bulk order of {line} eligible for a discount?",
                ],
            ),
        ],
    ),
    (
        "gift_cards",
        "Gift cards for {line}",
        [
            (
                "Gift cards for {line} are valid for {gy} years from the date of purchase.",
                {"gy": [2, 3]},
                ["{gy} years"],
                ["How long are gift cards for {line} valid?"],
            ),
        ],
    ),
    (
        "repairs",
        "Repairs of {line}",
        [
            (
                "Out-of-warranty repairs of {line} start at {rp} plus parts.",
                {"rp": ["€25", "€30", "€40"]},
                ["{rp}"],
                ["How much do out-of-warranty repairs of {line} cost?"],
            ),
            (
                "A repaired item from the {line} range is sent back within {rd} days.",
                {"rd": [10, 14, 21]},
                ["{rd} days"],
                ["How quickly is a repaired item from the {line} range sent back?"],
            ),
        ],
    ),
    (
        "damaged",
        "Damaged deliveries of {line}",
        [
            (
                "Report damaged {line} within {dd} hours of delivery to get a free replacement.",
                {"dd": [24, 48, 72]},
                ["{dd} hours"],
                ["How soon must I report damaged {line} after delivery?"],
            ),
        ],
    ),
]

# Extra phrasings so every row asks a distinct question (no dev/test leakage).
EXTRA_QUESTIONS: dict[str, list[tuple[int, str]]] = {
    "returns": [
        (0, "What is the return window for unused {line}?"),
        (0, "Can unused {line} be returned, and for how many days?"),
        (1, "When will my refund for returned {line} reach my payment method?"),
        (1, "How many business days until a refund for returned {line} reaches my payment method?"),
    ],
    "warranty": [
        (0, "How many years of warranty do {line} have?"),
        (0, "Is there a warranty against defects on {line}?"),
        (1, "Which documents does a warranty claim for {line} need?"),
        (1, "What does a warranty claim for {line} need?"),
    ],
    "shipping_cost": [
        (0, "What does standard shipping of {line} cost?"),
        (0, "When is standard shipping free for {line} orders?"),
        (0, "How much do I pay for standard shipping of {line}?"),
    ],
    "delivery_time": [
        (0, "Until what time can I order {line} for same-day shipping?"),
        (1, "How long does standard delivery of {line} take?"),
        (0, "When must {line} orders be placed to ship the same business day?"),
        (1, "How many business days should I expect for standard delivery of {line}?"),
    ],
    "support_hours": [
        (0, "When can I call the {line} support team on weekdays?"),
        (1, "What time does the {line} support chat close on Saturdays?"),
        (0, "From what time does the {line} support team answer calls on weekdays?"),
        (1, "Is the {line} support chat open on Saturdays, and until when?"),
    ],
    "price_match": [
        (0, "How long after purchase can I ask for a price match on {line}?"),
        (0, "Do you match the price of {line} sold by another shop, and for how many days?"),
        (0, "What is the price match period for {line}?"),
    ],
    "bulk": [
        (0, "Is there a discount for bulk orders of {line}?"),
        (0, "What percentage off do bulk orders of {line} get?"),
        (0, "From how many units does a bulk discount on {line} apply?"),
    ],
    "gift_cards": [
        (0, "For how many years can I use gift cards for {line}?"),
        (0, "Do gift cards for {line} expire?"),
        (0, "What is the validity period of gift cards for {line}?"),
    ],
    "repairs": [
        (0, "What is the starting price for out-of-warranty repairs of {line}?"),
        (1, "How long until a repaired item from the {line} range is sent back?"),
        (0, "What do out-of-warranty repairs of {line} start at?"),
        (1, "How many days until a repaired item from the {line} range is sent back?"),
    ],
    "damaged": [
        (0, "What is the deadline to report damaged {line} after delivery?"),
        (0, "How many hours do I have to report damaged {line}?"),
        (0, "Within how many hours should damaged {line} be reported for a free replacement?"),
    ],
}


def _fill(template: str, values: dict[str, Any]) -> str:
    return template.format(**values)


def build_corpus() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return (documents, facts). 10 schemas x 2 lines x 2 regions = 40 documents."""
    r = rng("faq_corpus")
    docs: list[dict[str, Any]] = []
    facts: list[dict[str, Any]] = []
    regions = ["online store", "retail stores"]
    for topic, title_t, schema_facts in SCHEMAS:
        for line in LINES:
            for region in regions:
                values: dict[str, Any] = {"line": line}
                for _, slots, _, _ in schema_facts:
                    for key, choices in slots.items():
                        values[key] = r.choice(choices)
                doc_id = f"faq-{len(docs) + 1:02d}"
                intro = f"This page explains {topic.replace('_', ' ')} for {line} bought in our {region}."
                sentences = [intro]
                extras = EXTRA_QUESTIONS.get(topic, [])
                for k, (sentence_t, _slots, key_t, base_questions) in enumerate(schema_facts):
                    questions_t = base_questions + [q for idx, q in extras if idx == k]
                    sentence = _fill(sentence_t, values)
                    sentence = sentence[:-1] + f" in our {region}."
                    sentences.append(sentence)
                    facts.append(
                        {
                            "doc_id": doc_id,
                            "sentence": sentence,
                            "key_facts": [_fill(k, values) for k in key_t],
                            "questions": [_fill(q, values)[:-1] + f" in your {region}?" for q in questions_t],
                            "topic": topic,
                            "line": line,
                            "region": region,
                        }
                    )
                sentences.append(f"Contact {COMPANY} support if you have more questions.")
                docs.append(
                    {
                        "id": doc_id,
                        "title": _fill(title_t, values) + f" ({region})",
                        "text": " ".join(sentences),
                        "topic": topic,
                        "line": line,
                        "region": region,
                    }
                )
    return docs, facts


PARAPHRASE_PREFIXES = ["Quick question: ", "Hello! ", "", "", "", ""]


def generate(n: int = 150, n_dev: int = 90) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    docs, facts = build_corpus()
    r: random.Random = rng("answer")
    pool = [(f, q) for f in facts for q in f["questions"]]
    r.shuffle(pool)
    pool = pool[:n] if len(pool) >= n else pool + [pool[i % len(pool)] for i in range(n - len(pool))]
    rows: list[dict[str, Any]] = []
    for i, (fact, question) in enumerate(pool):
        rows.append(
            {
                "id": f"ans-{i + 1:03d}",
                "split": "",
                "input": {"question": r.choice(PARAPHRASE_PREFIXES) + question},
                "expected": {
                    "answer": fact["sentence"],
                    "key_facts": fact["key_facts"],
                    "doc_id": fact["doc_id"],
                    "tools": [
                        {"name": "search_faq"},
                        {"name": "read_doc", "args_subset": {"doc_id": fact["doc_id"]}},
                    ],
                },
                "tags": [fact["topic"], fact["line"].replace(" ", "_")],
                "meta": {"generator": "answer", "region": fact["region"]},
            }
        )
    topics = [row["tags"][0] for row in rows]
    for row, split in zip(rows, stratified_splits(topics, n_dev / n, r), strict=True):
        row["split"] = split
    corpus = [
        {
            "id": d["id"],
            "split": "dev",
            "input": {"title": d["title"], "text": d["text"]},
            "expected": None,
            "tags": [d["topic"], d["line"].replace(" ", "_")],
            "meta": {"region": d["region"]},
        }
        for d in docs
    ]
    return rows, corpus
