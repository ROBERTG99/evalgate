"""Prompt-injection screening of candidate outputs before they reach a judge."""

from __future__ import annotations

import re
import unicodedata
from functools import cache
from importlib import resources

import yaml


@cache
def patterns() -> list[re.Pattern[str]]:
    text = resources.files("evalgate.judge").joinpath("injection_patterns.yaml").read_text(encoding="utf-8")
    data = yaml.safe_load(text)
    return [re.compile(p, re.IGNORECASE | re.MULTILINE) for p in data["patterns"]]


ZERO_WIDTH = re.compile("[\u00ad\u200b-\u200f\u2060-\u2064\ufeff]")


def normalise(text: str) -> str:
    """NFKC (full-width and compatibility forms to ASCII) without zero-width characters."""
    return ZERO_WIDTH.sub("", unicodedata.normalize("NFKC", text))


def injection_match(text: str) -> str | None:
    """Return the first matching phrase, or None."""
    text = normalise(text)
    for pattern in patterns():
        m = pattern.search(text)
        if m:
            return m.group(0)[:80]
    return None
