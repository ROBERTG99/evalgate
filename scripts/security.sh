#!/usr/bin/env bash
# make security: gitleaks, bandit, pip-audit, licenses and trivy on both images (high/critical fail).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PATH="$ROOT/.tools/bin:$PATH"
RUN="uv run --frozen"
mkdir -p dist

echo "== gitleaks (working tree and history)"
gitleaks git --no-banner --redact --exit-code 1 --config .gitleaks.toml .

echo "== bandit (src/)"
$RUN bandit -q -r src/evalgate -c pyproject.toml -ll

echo "== pip-audit (locked dependencies)"
uv export --frozen --all-extras --no-emit-workspace --no-hashes -o dist/requirements-audit.txt >/dev/null
# Documented exceptions (docs/security.md#dependency-findings): both only arrive with the optional [ragas]
# extra and have no fixed release yet.
$RUN pip-audit --strict --progress-spinner off -r dist/requirements-audit.txt \
  --ignore-vuln PYSEC-2026-2447 --ignore-vuln PYSEC-2026-3046

echo "== licenses"
$RUN python scripts/check_licenses.py

echo "== trivy (images)"
if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
  for image in evalgate toy-targets; do
    tag="evalgate-scan/${image}:local"
    docker build -q --network host --build-arg "HTTPS_PROXY=${HTTPS_PROXY:-}" -f "docker/${image}.Dockerfile" -t "$tag" . >/dev/null
    trivy image --quiet --scanners vuln --severity HIGH,CRITICAL --ignore-unfixed --exit-code 1 \
      --ignorefile .trivyignore "$tag"
  done
else
  echo "docker is not available: image scan skipped (recorded in docs/security.md)" >&2
  exit 1
fi
echo "security: clean"
