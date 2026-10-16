import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))
import check_contrast  # noqa: E402


def test_pairs_at_least_4_5() -> None:
    themes = check_contrast.parse(check_contrast.TOKENS.read_text())
    assert set(themes) == {"light", "dark"}
    assert themes["light"]["color-paper"].upper() == "#F7F7F2"
    assert themes["dark"]["color-paper"].upper() == "#0F1216"
    rows = check_contrast.pairs(themes)
    assert len(rows) == 2 * len(check_contrast.TEXT) * len(check_contrast.TEXT_ON)
    failing = [r for r in rows if r[3] < 4.5]
    assert failing == []


def test_reference_ratio() -> None:
    assert abs(check_contrast.ratio("#000000", "#FFFFFF") - 21.0) < 1e-9


def test_no_literal_colours_outside_tokens() -> None:
    static = ROOT / "src/evalgate/viewer/static"
    for path in [
        static / "app.css",
        *(ROOT / "src/evalgate/viewer/templates").glob("*.html"),
        *(ROOT / "src/evalgate/report/templates").glob("*.j2"),
    ]:
        text = path.read_text()
        assert not re.search(r"#[0-9A-Fa-f]{3,6}\b(?![\w-])", text.replace('href="#main"', "")), path
        assert "rgb(" not in text, path
