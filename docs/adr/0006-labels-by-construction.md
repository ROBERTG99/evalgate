# ADR-0006: Judge calibration labels by construction, and their limit

- Status: Accepted
- Date: 2026-10-16

## Context

A judge rubric is adopted only after calibration against labelled items: agreement, Cohen's kappa, position inconsistency and verbosity bias must meet the rubric's thresholds (`agreement_min` 0.80, `kappa_min` 0.70, `position_inconsistency_max` 0.10, `verbosity_bias_max` 0.05 in [evals/rubrics/](../../evals/rubrics/)). All data in this repository is synthetic, no human annotators were available during the build, and no provider key was available either, so no live model could be calibrated ([evals/reports/live-eval.json](../../evals/reports/live-eval.json) records `"ran": false`, reason `ANTHROPIC_API_KEY not set`).

## Decision

Generate the calibration labels by construction with the seeded generator (version 1.0.0, seed 1337) in [data/generator/judge.py](../../data/generator/judge.py). Each item starts from a known FAQ fact and applies a known transformation whose correct label follows from the transformation:

- [evals/datasets/judge/answer_correctness.labels.v1.jsonl](../../evals/datasets/judge/answer_correctness.labels.v1.jsonl): 200 items (120 dev, 80 test), built from exact copies, preambles, extra sentences, missing facts, wrong numbers, wrong documents, negations, numbers written as words, 20 injection items and 40 pairwise items (decisive, tie and hard).
- [evals/datasets/judge/rubric_adherence.labels.v1.jsonl](../../evals/datasets/judge/rubric_adherence.labels.v1.jsonl): 60 items (36 dev, 24 test) for the likert rubric, with binary labels (adherent equals rating 5).
- Every row has `"source": "construction"` and records the transformation in `meta.construction`. A few transformations are deliberately hard (numbers as words, negations, unusual citation formats) so that a judge cannot agree perfectly.

`make calibrate` ([scripts/calibrate_all.py](../../scripts/calibrate_all.py)) scores every rubric on its `test` labels with the same calibration function that backs `evalgate calibrate` ([src/evalgate/judge/calibrate.py](../../src/evalgate/judge/calibrate.py)); rubric work iterates on `dev` only (`evalgate calibrate --split dev`).

## Alternatives considered

- **Human labels from the start (rejected for v0.1.0).** They are the right ground truth for "does the judge agree with people", but none were available during the build, and inventing them would violate the synthetic-data rule. They remain the next step: the maintainer review below.
- **Labels produced by a stronger LLM (rejected).** Calibrating one model against another model's labels measures agreement between models, not correctness, and would need a provider key that was not available.
- **No calibration until human labels exist (rejected).** The bias controls (position swap, verbosity probe, injection guard) and the calibration code itself would then ship untested against any known answer.

## Consequences

### Positive

- Calibration runs offline and deterministically in CI. On the `test` split, offline: `answer_correctness` agreement 0.875, kappa 0.746283 on 64 items with 8 injection items and 0 pass-through; `pairwise_preference` agreement 0.875, kappa 0.811765 on 16 items; `rubric_adherence` agreement 0.916667, kappa 0.823529 on 24 items; position inconsistency and verbosity bias 0.0 for all three ([evals/reports/calibration-answer_correctness.json](../../evals/reports/calibration-answer_correctness.json), [calibration-pairwise_preference.json](../../evals/reports/calibration-pairwise_preference.json), [calibration-rubric_adherence.json](../../evals/reports/calibration-rubric_adherence.json), `make calibrate`).
- Because the correct answer of every item is known, a failure points at a specific transformation, which makes the bias and injection controls testable.

### Negative

- **The limit.** Labels by construction prove that the judge pipeline and its bias controls work on items with known answers: rendering, schema validation, position swap, verbosity probe, injection blocking and the agreement and kappa arithmetic. They do not prove that a real model agrees with human judgment on real data. The offline numbers above come from FakeJudge, a rule-based judge whose rules and the construction rules share the same notion of "key facts", so high agreement there is expected and is not evidence about any LLM.
- The construction types cover a narrow set of errors (facts, numbers, citations, length). Real outputs fail in ways the generator does not produce.
- A maintainer review of 40 labels is pending ("Needs the maintainer" in [PROGRESS.md](../../PROGRESS.md)); reviewed rows will be marked `"source": "maintainer"` in a new `labels.v2` file, because committed label files are append-only by version. Live calibration also waits for a provider key (`make eval-live`). Both gaps are listed in [docs/KNOWN_LIMITATIONS.md](../KNOWN_LIMITATIONS.md).
