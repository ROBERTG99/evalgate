---
name: release
description: Prepare an evalgate release locally (CHANGELOG, version in pyproject.toml, build, local tag v0.1.0). Use for task T-44 or any later version. Pushing tags, GitHub Releases and PyPI publishing are maintainer only.
---

# Release

The release workflow `.github/workflows/release.yml` runs on a pushed `v*` tag. Creating the tag locally is your job; pushing it is the maintainer's.

## Steps

1. Run the `quality-gate` skill up to `make verify`; it must be green with no API keys, and the `reviewer` subagent must report `Verdict: ship`.
2. Set the version in `pyproject.toml` (`[project] version`, for example `0.1.0`) and keep `evalgate.__version__` in `src/evalgate/__init__.py` consistent.
3. Update `CHANGELOG.md` (Keep a Changelog format): move "Unreleased" items under `## [0.1.0] - YYYY-MM-DD`, grouped as Added, Changed, Fixed, Security. Every number in it cites its report or command.
4. Check consistency:

   ```bash
   uv run pytest tests/harness/test_release.py -q   # version matches CHANGELOG
   make build                                      # wheel and sdist, < 1 MB
   make sbom                                       # dist/sbom.cdx.json
   ```

5. Commit with `chore(release): v0.1.0` (no attribution trailers).
6. Create the local annotated tag only:

   ```bash
   git tag -a v0.1.0 -m "evalgate v0.1.0"
   ```

   Never run `git push --tags`, `git push origin v0.1.0`, `gh release create` or a PyPI upload; the `pre_tool_guard.py` hook blocks them.
7. Add "Push tag `v0.1.0` to trigger `release.yml` (GitHub Release, PyPI trusted publishing, GHCR images)" under "Needs the maintainer" in `PROGRESS.md`, and update `docs/runbook.md` (release, tag rollback, baseline rotation) if the process changed.
8. Push the current branch only (`git push -u origin <branch>`) if a remote exists.
