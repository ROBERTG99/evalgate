#!/usr/bin/env bash
# make verify-clean: §19 step 1. Clone the committed repository into a temporary folder and run
# `make bootstrap && make verify` there with no .env file and no provider keys.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST="${VERIFY_DIR:-/tmp/verify-evalgate}"
if [ -n "$(git -C "$ROOT" status --porcelain)" ]; then
  echo "verify-clean: uncommitted changes are not part of the clone; commit first" >&2
fi
rm -rf "$DEST"
git clone --quiet "$ROOT" "$DEST"
cd "$DEST"
rm -f .env
start=$(date +%s)
env -u ANTHROPIC_API_KEY -u OPENAI_API_KEY -u AWS_ACCESS_KEY_ID -u AWS_SECRET_ACCESS_KEY \
  make bootstrap verify
echo "verify-clean: passed in $(( $(date +%s) - start )) s at $(git rev-parse --short HEAD) in $DEST"
