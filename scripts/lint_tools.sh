#!/usr/bin/env bash
# Non-Python linters for make lint: markdownlint-cli2, shellcheck, hadolint, actionlint.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PATH="$ROOT/.tools/bin:$PATH"
echo "== markdownlint"
markdownlint-cli2
echo "== shellcheck"
shellcheck scripts/*.sh .claude/hooks/*.sh
echo "== hadolint"
hadolint docker/*.Dockerfile
echo "== actionlint"
actionlint
echo "lint: clean"
