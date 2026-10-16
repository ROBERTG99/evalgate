#!/usr/bin/env bash
# make seed: run the v1 and v2 toy suites (offline, seed 1337) into the viewer's reports volume.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
docker compose --profile tools run --rm seed
echo "seed: open http://localhost:8100"
