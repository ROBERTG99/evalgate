"""Regenerate every synthetic dataset (seed 1337). ``--check`` verifies committed files and MANIFEST.json.

Usage: ``uv run python -m data.generator [--check] [--out DIR]``
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from data.generator import answer, classify, extract, judge, meta, promptfoo
from data.generator.common import dump_jsonl, manifest, sha256_text, write_all

ROOT = Path(__file__).resolve().parents[2]
DATASETS = "evals/datasets"


def build() -> dict[str, str]:
    answer_rows, corpus = answer.generate()
    files = {
        f"{DATASETS}/toys/classify.v1.jsonl": dump_jsonl(classify.generate()),
        f"{DATASETS}/toys/extract.v1.jsonl": dump_jsonl(extract.generate()),
        f"{DATASETS}/toys/answer.v1.jsonl": dump_jsonl(answer_rows),
        f"{DATASETS}/toys/faq_corpus.v1.jsonl": dump_jsonl(corpus),
        f"{DATASETS}/meta/variants.v1.jsonl": dump_jsonl(meta.generate()),
        f"{DATASETS}/judge/answer_correctness.labels.v1.jsonl": dump_jsonl(judge.generate_answer_correctness()),
        f"{DATASETS}/judge/rubric_adherence.labels.v1.jsonl": dump_jsonl(judge.generate_rubric_adherence()),
        f"{DATASETS}/promptfoo/promptfooconfig.yaml": promptfoo.generate(),
    }
    files[f"{DATASETS}/MANIFEST.json"] = json.dumps(manifest(files), indent=2) + "\n"
    return files


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail if committed files differ from a regeneration")
    parser.add_argument("--out", type=Path, default=ROOT)
    args = parser.parse_args()
    files = build()
    if args.check:
        bad = []
        for rel, text in files.items():
            path = args.out / rel
            if not path.exists() or sha256_text(path.read_text(encoding="utf-8")) != sha256_text(text):
                bad.append(rel)
        if bad:
            print("datasets differ from a seed-1337 regeneration: " + ", ".join(bad), file=sys.stderr)
            return 1
        print(f"datasets: {len(files)} files match MANIFEST.json and the generator (seed 1337)")
        return 0
    existing = [
        rel for rel in files if (args.out / rel).exists() and (args.out / rel).read_text(encoding="utf-8") != files[rel]
    ]
    if existing and args.out == ROOT:
        print(
            "refusing to overwrite committed datasets (append-only): "
            + ", ".join(existing)
            + "; add a new version instead",
            file=sys.stderr,
        )
        return 1
    write_all(args.out, files)
    print(f"datasets: wrote {len(files)} files under {args.out / DATASETS}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
