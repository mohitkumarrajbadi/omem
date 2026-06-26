#!/usr/bin/env bash
# cloud-docker-smoke.sh — Quick smoke test against local Docker + Postgres stack.

set -euo pipefail

BASE="${OMEM_ENDPOINT:-http://localhost:8080}"
HDR=(-H "Content-Type: application/json")
if [[ -n "${OMEM_API_KEY:-}" ]]; then
  HDR+=(-H "Authorization: Bearer $OMEM_API_KEY")
fi

echo "==> Health"
curl -sf "$BASE/v1/health" | python3 -m json.tool

echo "==> Remember"
curl -sf -X POST "$BASE/v1/remember" "${HDR[@]}" \
  -d '{"content":"Cloud Docker + Postgres smoke test","session_id":"smoke","importance":0.9}'

echo ""
echo "==> Recall"
curl -sf -X POST "$BASE/v1/recall" "${HDR[@]}" \
  -d '{"query":"Postgres smoke","session_id":"smoke","k":3}' | python3 -m json.tool

echo ""
echo "==> Checkpoint"
curl -sf -X POST "$BASE/v1/state/smoke/checkpoint" "${HDR[@]}" | python3 -m json.tool

echo ""
echo "Smoke test OK — backend should report postgres in /v1/health"
