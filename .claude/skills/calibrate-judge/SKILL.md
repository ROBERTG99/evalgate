---
name: calibrate-judge
description: Create or change an LLM-judge rubric and calibrate it against labelled items before adoption. Use when adding a rubric in evals/rubrics/, changing a prompts/judge_*.vN.md prompt, or switching the judge model.
---

# Calibrate a judge

A judge is adopted only if, on the `test` labels, agreement ≥ 0.80 and Cohen's kappa ≥ 0.70, with position inconsistency ≤ 0.10, verbosity bias ≤ 0.05 and zero injection pass-through (`.claude/rules/evals.md`).

## Steps

1. Write or version the rubric in `evals/rubrics/<name>.vN.yaml` (`schema: evalgate.rubric.v1`, `mode: pointwise|pairwise`, `scale: binary|likert5`, `prompt`, `route: judge|judge_hard`, `criteria`, `thresholds`, `position_swap`, `verbosity_probe`). A changed prompt is a new file `prompts/judge_<name>.v<N+1>.md`; never edit a released version.
2. Check the labels in `evals/datasets/judge/` (for example `answer_correctness.labels.v1.jsonl`: 200 items, 120 dev and 80 test, with 20 injection and 40 pairwise items). New labels come from the generator through the `add-eval-case` skill, never by hand.
3. Iterate on the `dev` split only:

   ```bash
   uv run evalgate calibrate --rubric evals/rubrics/answer_correctness.v1.yaml \
     --labels evals/datasets/judge/answer_correctness.labels.v1.jsonl --split dev
   ```

   Read the confusion matrix, position inconsistency and verbosity bias; adjust the prompt or rubric, not the labels. Check the flags with `uv run evalgate calibrate --help`; if there is no way to restrict to `dev`, add one through the `tdd` skill instead of reading `test` results while iterating.
4. Freeze the rubric, then run once on `test`:

   ```bash
   make calibrate   # scripts/calibrate_all.py, every rubric on its test labels
   ```

   It exits 1 if agreement < 0.80 or kappa < 0.70.
5. Adopt only on a pass: reference the rubric from the suite in `evals/suites/`. On a fail, do not tune on `test`; go back to step 3 with a new prompt version, or record the gap in `docs/KNOWN_LIMITATIONS.md`.
6. Confirm the injection and bias tests still pass: `uv run pytest tests/unit/judge -q`.
7. Run the `eval-analyst` subagent on `evals/reports/`, regenerate `evals/REPORT.md` with `make eval`, and cite the numbers with their report paths in the pull request. A live check of the same rubric runs only through `make eval-live`.
