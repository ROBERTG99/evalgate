import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

from data.generator.__main__ import build
from data.generator.common import sha256_text

ROOT = Path(__file__).resolve().parents[3]
DATASETS = ROOT / "evals/datasets"


def test_manifest_hashes_match() -> None:
    manifest = json.loads((DATASETS / "MANIFEST.json").read_text())
    assert manifest["seed"] == 1337
    assert manifest["generator_version"] == "1.0.0"
    for rel, info in manifest["files"].items():
        text = (ROOT / rel).read_text()
        assert sha256_text(text) == info["sha256"], rel
    regenerated = build()
    for rel, text in regenerated.items():
        assert (ROOT / rel).read_text() == text, f"{rel} is not byte-identical to a regeneration"


def test_check_command_passes() -> None:
    proc = subprocess.run(
        [sys.executable, "-m", "data.generator", "--check"], cwd=ROOT, capture_output=True, text=True, check=False
    )
    assert proc.returncode == 0, proc.stderr


def test_50_variants_and_200_labels() -> None:
    variants = [json.loads(x) for x in (DATASETS / "meta/variants.v1.jsonl").read_text().splitlines()]
    assert len(variants) == 50
    assert Counter(v["expected"]["regression"] for v in variants) == {True: 30, False: 20}
    assert Counter(v["split"] for v in variants) == {"dev": 30, "test": 20}
    labels = [json.loads(x) for x in (DATASETS / "judge/answer_correctness.labels.v1.jsonl").read_text().splitlines()]
    assert len(labels) == 200
    assert Counter(r["split"] for r in labels) == {"dev": 120, "test": 80}
    kinds = Counter(r["meta"]["construction"] for r in labels)
    assert kinds["injection"] == 20
    assert sum(1 for r in labels if r["candidate_b"] is not None) == 40
    assert all(r["label"] == 0 for r in labels if r["meta"]["construction"] == "injection")
