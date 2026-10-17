---
name: new-adr
description: Write a new Architecture Decision Record in docs/adr/. Use when a choice affects architecture, contracts, dependencies or the gate semantics of evalgate (for example ADR-0001 to ADR-0007 of the build spec §18).
---

# New ADR

Architectural choices get an ADR in `docs/adr/`; smaller decisions only go in `docs/DECISIONS.md`.

## Steps

1. Find the next number:

   ```bash
   ls docs/adr/ | sort | tail -n 3
   ```

   Files are named `docs/adr/NNNN-short-kebab-title.md` (four digits, for example `0003-paired-bootstrap-over-t-test.md`).
2. Collect the facts: the problem, constraints from `docs/specs/000-build-spec.md` (or `BUILD.md`), and any measurement. A number in the ADR cites the command or report that produced it; if nothing was measured, say so.
3. Create the file with this structure:

   ```markdown
   # ADR-NNNN: <decision in a few words>

   - Status: Accepted
   - Date: YYYY-MM-DD

   ## Context

   ## Decision

   ## Rejected alternative

   ## Consequences
   ```

   The rejected alternative is mandatory (for example SQLite and Postgres for ADR-0001, LiteLLM for ADR-0002, a paired t-test for ADR-0003).
4. Link code by relative path, for example `[src/evalgate/stats/](../../src/evalgate/stats/)`.
5. Add a one-line entry to `docs/DECISIONS.md` (date, decision, alternatives, reason, link to the ADR).
6. If the decision supersedes an older ADR, set the old one's status to `Superseded by ADR-NNNN`; never delete an ADR.
7. Lint: `.tools/bin/markdownlint-cli2 "docs/adr/*.md"` (or `make lint`), then commit with `docs: add ADR-NNNN <title>`.
