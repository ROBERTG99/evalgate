#!/usr/bin/env bash
# SessionStart hook: prepares Claude Code on the web containers (Appendix A of the build spec).
# Idempotent; does nothing on local runs.
set -euo pipefail

if [[ "${CLAUDE_CODE_REMOTE:-}" != "true" ]]; then
  exit 0
fi

ROOT="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
cd "$ROOT"

# Docker daemon through the registry mirror (Docker Hub direct pulls are rate limited).
if command -v dockerd >/dev/null 2>&1 && ! docker info >/dev/null 2>&1; then
  mkdir -p /etc/docker
  if [[ ! -f /etc/docker/daemon.json ]]; then
    echo '{"registry-mirrors":["https://mirror.gcr.io"]}' > /etc/docker/daemon.json
  fi
  (nohup dockerd > /tmp/dockerd.log 2>&1 &)
  for _ in $(seq 1 30); do docker info >/dev/null 2>&1 && break; sleep 1; done
fi

./scripts/install_tools.sh >/dev/null
uv sync --frozen --all-extras >/dev/null 2>&1 || uv sync --all-extras
[[ -f .env ]] || cp .env.example .env

if [[ -n "${CLAUDE_ENV_FILE:-}" ]]; then
  echo "export PATH=\"$ROOT/.tools/bin:\$PATH\"" >> "$CLAUDE_ENV_FILE"
fi
echo "evalgate session ready: tools in .tools/bin, venv in .venv"
