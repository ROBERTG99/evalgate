"""PII redaction applied by the gateway before any provider call: emails, phone numbers, card numbers."""

from __future__ import annotations

import re

EMAIL = re.compile(r"[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9-]{1,63}(?:\.[A-Za-z0-9-]{1,63}){0,8}\.[A-Za-z]{2,24}")
CARD = re.compile(r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)")
PHONE = re.compile(r"(?<![\w])(?:\+\d{1,3}[ .-]?)?(?:\(\d{2,4}\)[ .-]?)?\d{2,4}(?:[ .-]\d{2,4}){2,4}(?![\w])")


def luhn_ok(digits: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def _card(match: re.Match[str]) -> str:
    digits = re.sub(r"\D", "", match.group(0))
    return "[CARD]" if 13 <= len(digits) <= 19 and luhn_ok(digits) else match.group(0)


DATE = re.compile(r"\d{4}-\d{2}-\d{2}|\b\d{1,2}[./]\d{1,2}[./]\d{4}\b")


def _phone(match: re.Match[str]) -> str:
    if DATE.search(match.group(0)):
        return match.group(0)
    digits = re.sub(r"\D", "", match.group(0))
    return "[PHONE]" if 9 <= len(digits) <= 15 else match.group(0)


MAX_REDACT_CHARS = 200_000


def redact(text: str) -> str:
    """Replace emails, Luhn-valid card numbers and phone numbers with placeholders.

    Every pattern uses bounded quantifiers, so the cost is linear in the input; text beyond
    ``MAX_REDACT_CHARS`` is cut (it would not fit a judge prompt anyway)."""
    if len(text) > MAX_REDACT_CHARS:
        text = text[:MAX_REDACT_CHARS] + " [TRUNCATED]"
    text = EMAIL.sub("[EMAIL]", text)
    text = CARD.sub(_card, text)
    return PHONE.sub(_phone, text)
