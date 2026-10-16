#!/usr/bin/env bash
# make test-docker: unit, integration, contract (against real WireMock 8142/8143) and harness tests,
# Playwright + axe E2E against the seeded stack, and promtool rule tests, all in containers.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
# The e2e container runs as the host user (never root) and writes screenshots to docs/images.
HOST_UID="$(id -u)"
HOST_GID="$(id -g)"
export HOST_UID HOST_GID
docker compose up -d --build --wait
docker compose --profile tools run --rm seed >/dev/null
TEST="docker compose -f compose.test.yaml"
$TEST build tests e2e
status=0
$TEST run --rm tests || status=1
$TEST run --rm e2e || status=1
$TEST run --rm promtool || status=1
$TEST down --remove-orphans >/dev/null 2>&1 || true
if [ "$status" -ne 0 ]; then echo "test-docker: FAILED"; exit 1; fi
echo "test-docker: passed"
