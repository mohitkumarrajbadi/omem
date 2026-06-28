#!/usr/bin/env bash
# cloud-docker-smoke.sh — Minimal smoke test for the Docker cloud stack.
# Covers: health, remember, recall, context/build, checkpoint, status, metrics.

set -euo pipefail

BASE="${OMEM_ENDPOINT:-http://localhost}"
BASE="${BASE%/}"
SESSION="${OMEM_SESSION:-smoke-$(date +%s)}"

HDR=(
  -H "Content-Type: application/json"
  -H "X-OMem-Session: $SESSION"
)

if [[ -n "${OMEM_API_KEY:-}" ]]; then
  HDR+=(-H "Authorization: Bearer $OMEM_API_KEY")
fi

echo "==> Health check"
curl -sf "$BASE/v1/health" | python3 -m json.tool

echo ""
echo "==> Remember (content-only body — importance inferred)"
curl -sf -X POST "$BASE/v1/remember" "${HDR[@]}" \
  -d '{"content":"Cloud Docker + Postgres smoke test passed"}' | python3 -m json.tool

echo ""
echo "==> Recall (query only)"
curl -sf -X POST "$BASE/v1/recall" "${HDR[@]}" \
  -d '{"query":"Docker smoke test", "k": 3}' | python3 -m json.tool

echo ""
echo "==> Context build (token savings)"
curl -sf -X POST "$BASE/v1/context/build" "${HDR[@]}" \
  -d '{"task":"summarise smoke test results", "budget_tokens": 2048}' | python3 -m json.tool

echo ""
echo "==> Status dashboard"
curl -sf "$BASE/v1/status" "${HDR[@]}" | python3 -m json.tool

echo ""
echo "==> Checkpoint"
curl -sf -X POST "$BASE/v1/state/$SESSION/checkpoint" "${HDR[@]}" | python3 -m json.tool

echo ""
echo "==> Prometheus metrics (first 15 lines)"
curl -sf "$BASE/v1/metrics" | head -15

echo ""
echo "Smoke test OK"
echo "  Session: $SESSION"
echo "  Swagger: $BASE/docs"
