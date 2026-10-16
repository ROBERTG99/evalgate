"""WCAG 2.2 contrast check of the viewer tokens in light and dark themes (text pairs >= 4.5:1)."""

from __future__ import annotations

import re
import sys
from pathlib import Path

TOKENS = Path(__file__).resolve().parents[1] / "src/evalgate/viewer/static/tokens.css"
TEXT_ON = ["color-paper", "color-surface", "color-row-alt"]
TEXT = ["color-ink", "color-muted", "color-pass", "color-fail", "color-regression", "color-focus"]
MIN_RATIO = 4.5


def parse(css: str) -> dict[str, dict[str, str]]:
    blocks = {"light": css.split("@media", maxsplit=1)[0], "dark": css.split(':root[data-theme="dark"]')[1]}
    out = {}
    for theme, block in blocks.items():
        out[theme] = dict(re.findall(r"--(color-[a-z-]+):\s*(#[0-9A-Fa-f]{6})", block))
    out["dark"] = {**out["light"], **out["dark"]}
    return out


def luminance(hex_color: str) -> float:
    rgb = [int(hex_color[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    lin = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def ratio(a: str, b: str) -> float:
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def pairs(themes: dict[str, dict[str, str]]) -> list[tuple[str, str, str, float]]:
    rows = []
    for theme, tokens in themes.items():
        for fg in TEXT:
            for bg in TEXT_ON:
                rows.append((theme, fg, bg, ratio(tokens[fg], tokens[bg])))
    return rows


def main() -> int:
    rows = pairs(parse(TOKENS.read_text()))
    bad = [r for r in rows if r[3] < MIN_RATIO]
    for theme, fg, bg, value in rows:
        print(f"{theme:5} {fg:18} on {bg:15} {value:5.2f}:1 {'FAIL' if value < MIN_RATIO else 'ok'}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
