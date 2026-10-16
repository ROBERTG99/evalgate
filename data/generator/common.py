"""Shared helpers: seeded RNG streams, JSONL writing and the manifest."""

from __future__ import annotations

import hashlib
import json
import random
from pathlib import Path
from typing import Any

GENERATOR_VERSION = "1.0.0"
SEED = 1337


def rng(stream: str, seed: int = SEED) -> random.Random:
    """An independent, reproducible RNG per named stream (adding a stream never shifts another)."""
    digest = hashlib.sha256(f"{seed}:{stream}".encode()).digest()
    return random.Random(int.from_bytes(digest[:8], "big"))


def dump_jsonl(rows: list[dict[str, Any]]) -> str:
    return "".join(json.dumps(r, ensure_ascii=False, sort_keys=False) + "\n" for r in rows)


def assign_splits(n: int, n_dev: int, r: random.Random) -> list[str]:
    splits = ["dev"] * n_dev + ["test"] * (n - n_dev)
    r.shuffle(splits)
    return splits


def stratified_splits(labels: list[str], dev_fraction: float, r: random.Random) -> list[str]:
    """Split each label group with the same dev fraction (largest remainder keeps totals exact)."""
    out = [""] * len(labels)
    groups: dict[str, list[int]] = {}
    for i, label in enumerate(labels):
        groups.setdefault(label, []).append(i)
    target_dev = round(len(labels) * dev_fraction)
    quotas = {k: len(v) * dev_fraction for k, v in groups.items()}
    dev_counts = {k: int(q) for k, q in quotas.items()}
    remainder = sorted(groups, key=lambda k: (-(quotas[k] - dev_counts[k]), k))
    for k in remainder[: target_dev - sum(dev_counts.values())]:
        dev_counts[k] += 1
    for k, idx in groups.items():
        shuffled = idx[:]
        r.shuffle(shuffled)
        for j, i in enumerate(shuffled):
            out[i] = "dev" if j < dev_counts[k] else "test"
    return out


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def manifest(files: dict[str, str]) -> dict[str, Any]:
    return {
        "generator": "data/generator",
        "generator_version": GENERATOR_VERSION,
        "seed": SEED,
        "synthetic": True,
        "files": {
            path: {"sha256": sha256_text(text), "rows": text.count("\n") if path.endswith(".jsonl") else None}
            for path, text in sorted(files.items())
        },
    }


def write_all(root: Path, files: dict[str, str]) -> None:
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
