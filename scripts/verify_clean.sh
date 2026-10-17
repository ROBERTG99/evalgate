#!/usr/bin/env bash
# make verify-clean: §19 step 1. Clone the committed repository into a temporary folder and run
# `make bootstrap && make verify` there with no .env file and no provider keys.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST="${VERIFY_DIR:-$(mktemp -d "${TMPDIR:-/tmp}/verify-evalgate.XXXXXX")}"
if [ -n "$(git -C "$ROOT" status --porcelain)" ]; then
  echo "verify-clean: uncommitted changes are not part of the clone; commit first" >&2
fi
if [ -n "${VERIFY_DIR:-}" ]; then rm -rf "$DEST"; fi
git clone --quiet "$ROOT" "$DEST/repo"
DEST="$DEST/repo"
cd "$DEST"
rm -f .env
start=$(date +%s)
# No provider keys, cloud profiles, Langfuse or OTel settings, and no evalgate overrides: offline defaults only.
while read -r name; do unset "$name"; done < <(compgen -e | grep -E '^(ANTHROPIC|OPENAI|AWS|AZURE|GOOGLE|LANGFUSE|OTEL|EVALGATE)_' || true)
export EVALGATE_LLM_PROVIDER=fake
make bootstrap verify
echo "verify-clean: passed in $(( $(date +%s) - start )) s at $(git rev-parse --short HEAD) in $DEST"
