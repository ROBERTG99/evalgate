---
paths:
  - "evals/**"
  - "data/generator/**"
  - "scripts/meta_eval.py"
  - "scripts/build_eval_report.py"
---

# Evals

- Never tune prompts, rules or thresholds on the `test` split; use `dev`.
- Thresholds are only ever raised, never lowered.
- Datasets and baselines are append-only by version (`.vN.jsonl`, new baseline file); never edit a committed one.
- Every number in `evals/REPORT.md` comes from a report in `evals/reports/` written by a command.
- Regenerate data only with `make seed-data` (seed 1337) and check `MANIFEST.json`.
