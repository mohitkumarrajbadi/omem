#!/usr/bin/env bash
# Stranger stand-in: fresh venv, one install, init, demo.
# Prints the causing memory and the elapsed seconds.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
START=$(date +%s)
VENV="${WOW_VENV:-"$ROOT/.venv-wow"}"
DB="${WOW_DB:-"$(mktemp -d)/brain.db"}"

python3 -m venv "$VENV"
"$VENV/bin/pip" install -q "$ROOT[mcp]"
"$VENV/bin/omem" --db-path "$DB" init
"$VENV/bin/omem" --db-path "$DB" demo | tee /dev/stderr | grep -q "demo-stale-mongodb"
END=$(date +%s)
echo "elapsed_s=$((END - START))"
