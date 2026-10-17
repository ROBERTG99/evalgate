#!/usr/bin/env bash
# make demo: the scripted scenario, offline, against the running toy targets (docker compose up -d --wait).
#  1. A pull request ships classify v2. evalgate runs the suite and gates it against the committed v1
#     baseline: the paired bootstrap finds a regression and `evalgate check` exits 1.
#  2. The pull request switches back to v1: the same gate exits 0.
# Overrides: EVALGATE (command), EVALGATE_TOYS_URL, EVALGATE_DEMO_DIR (where reports go).
set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.." || exit 2

EVALGATE="${EVALGATE:-uv run --frozen evalgate}"
OUT="${EVALGATE_DEMO_DIR:-.evalgate/demo}"
SUITE=evals/suites/classify.yaml
BASELINE=evals/baselines/classify.json
export EVALGATE_TOYS_URL="${EVALGATE_TOYS_URL:-http://localhost:8110}"
export EVALGATE_HTTP_ALLOWED_HOSTS="${EVALGATE_HTTP_ALLOWED_HOSTS:-localhost,127.0.0.1}"
export EVALGATE_LLM_PROVIDER="${EVALGATE_LLM_PROVIDER:-fake}"
mkdir -p "$OUT"

healthy() { # no curl in slim images; any Python 3 will do
  python3 -c 'import sys, urllib.request; urllib.request.urlopen(sys.argv[1] + "/healthz", timeout=3)' \
    "$EVALGATE_TOYS_URL" >/dev/null 2>&1
}
if ! healthy; then
  echo "demo: toy targets are not reachable at $EVALGATE_TOYS_URL; run 'docker compose up -d --wait' first" >&2
  exit 2
fi

gate() { # gate <version> <expected exit>
  local version="$1" expected="$2" status
  echo
  echo "### classify $version: run the suite (offline, test split) and gate it against the v1 baseline"
  echo "\$ EVALGATE_TOY_VERSION=$version evalgate run $SUITE --out $OUT/classify-$version.json"
  EVALGATE_TOY_VERSION="$version" $EVALGATE run "$SUITE" --out "$OUT/classify-$version.json" || return 1
  echo "\$ evalgate check $OUT/classify-$version.json --baseline $BASELINE --max-regression-pp 1.0"
  $EVALGATE check "$OUT/classify-$version.json" --baseline "$BASELINE" --max-regression-pp 1.0 \
    --out-json "$OUT/check-$version.json"
  status=$?
  echo "evalgate check exited $status"
  [ "$status" -eq "$expected" ]
}

gate v2 1 || { echo "demo: expected the v2 candidate to fail the gate" >&2; exit 1; }
echo
echo "### The pull request switches back to v1"
gate v1 0 || { echo "demo: expected v1 to pass the gate" >&2; exit 1; }
echo
echo "demo: v2 blocked (exit 1), v1 passes (exit 0). Reports in $OUT; the seeded viewer is at http://localhost:8100"
