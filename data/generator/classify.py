"""Support-ticket classification rows (labels by construction)."""

from __future__ import annotations

import random
from typing import Any

from data.generator.common import rng, stratified_splits

LABELS = ["account_access", "billing", "bug_report", "cancellation", "feature_request", "shipping"]
PRODUCTS = ["garden hose", "desk lamp", "kettle", "backpack", "rain jacket", "blender", "office chair", "bike light"]
NAMES = ["Avery", "Jordan", "Riley", "Sam", "Morgan", "Casey", "Quinn", "Taylor", "Robin", "Dana"]
DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "the weekend"]

TEMPLATES: dict[str, list[str]] = {
    "account_access": [
        "I can't log in to my account since {day}, it keeps saying the password is wrong.",
        "The password reset link never arrives, so I am locked out of my profile.",
        "Two-factor codes are not accepted when I try to sign in from my new phone.",
        "I am locked out after too many attempts. Please help me get back into my account.",
        "My login stopped working after I changed my email address on {day}.",
    ],
    "billing": [
        "I was charged twice for my {product} order. Please refund the duplicate payment.",
        "The invoice for my last order shows the wrong amount, can you send a corrected receipt?",
        "My credit card payment failed but the money left my bank account on {day}.",
        "Why does my billing statement include a fee I never agreed to?",
        "Please send me a receipt for the {product} I bought, my accountant needs the invoice.",
    ],
    "bug_report": [
        "The app crashes every time I open the order history page.",
        "Checkout shows an error message when I add the {product} to the cart.",
        "The search page freezes on my laptop and nothing loads.",
        "The product photos are broken on the mobile site since {day}.",
        "Saving my address fails with a blank screen, this looks like a bug.",
    ],
    "cancellation": [
        "Please cancel my subscription, I no longer need the monthly box.",
        "I want to cancel the order for the {product} before it ships.",
        "How do I close my account and delete my saved details?",
        "Unsubscribe me from the premium plan starting next month.",
        "I would like to terminate my membership, it renews on {day}.",
    ],
    "feature_request": [
        "It would be great if the app supported a dark mode.",
        "Could you add a wish list so I can save the {product} for later?",
        "Suggestion: let us pick a delivery time window at checkout.",
        "Please add support for paying with a gift card and a card together.",
        "I wish there was a way to compare two products side by side.",
    ],
    "shipping": [
        "My {product} has not arrived and the tracking page has not changed since {day}.",
        "The courier left my parcel at the wrong address.",
        "When will my order be shipped? It has been a week.",
        "The delivery was marked complete but nothing arrived.",
        "Can I change the delivery address for the {product} that shipped yesterday?",
    ],
}

# Labelled by what the customer wants, but worded with another category's keywords: a keyword
# classifier that checks rules in a fixed order is expected to get these wrong.
HARD_TEMPLATES: dict[str, list[str]] = {
    "billing": ["I was charged again even though I asked to cancel last month, please fix the payment."],
    "shipping": ["My parcel arrived, but the invoice inside lists the wrong address for the delivery."],
    "feature_request": ["Could you add an option to cancel a single item from an order? That would be great."],
    "bug_report": ["The login page shows an error when I click the help link, the page is broken."],
}
HARD_RATE = 0.07


def _fill(template: str, r: random.Random) -> str:
    return template.format(product=r.choice(PRODUCTS), day=r.choice(DAYS))


def generate(n: int = 150, n_dev: int = 90) -> list[dict[str, Any]]:
    r = rng("classify")
    labels = [LABELS[i % len(LABELS)] for i in range(n)]
    r.shuffle(labels)
    rows: list[dict[str, Any]] = []
    for i, label in enumerate(labels):
        hard = label in HARD_TEMPLATES and r.random() < HARD_RATE * len(LABELS) / len(HARD_TEMPLATES)
        template = r.choice(HARD_TEMPLATES[label] if hard else TEMPLATES[label])
        text = _fill(template, r)
        if r.random() < 0.4:
            text = f"Hi, this is {r.choice(NAMES)}. {text}"
        if r.random() < 0.3:
            text += " Thanks!"
        rows.append(
            {
                "id": f"cls-{i + 1:03d}",
                "split": "",
                "input": {"text": text},
                "expected": {"label": label},
                "tags": [label] + (["hard"] if hard else []),
                "meta": {"generator": "classify", "template": "hard" if hard else "standard"},
            }
        )
    for row, split in zip(rows, stratified_splits(labels, n_dev / n, r), strict=True):
        row["split"] = split
    return rows
