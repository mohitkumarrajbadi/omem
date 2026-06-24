#!/usr/bin/env bash
# health-check.sh — smoke test the deployed OMem Cloud API.
#
# Usage:
#   ./deploy/scripts/health-check.sh [https://state-preview.akamai.ai]
#
# Requires: curl, jq

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TERRAFORM_DIR="$SCRIPT_DIR/../linode/terraform"

ENDPOINT="${1:-}"

# Auto-resolve from Terraform state if not provided
if [[ -z "$ENDPOINT" ]]; then
  cd "$TERRAFORM_DIR"
  API_IP=$(terraform output -raw api_ip 2>/dev/null || echo "")
  if [[ -n "$API_IP" ]]; then
    ENDPOINT="https://$API_IP"
  else
    echo "ERROR: No endpoint provided and Terraform state not found."
    echo "Usage: $0 https://state-preview.akamai.ai"
    exit 1
  fi
fi

echo "==> Health check: $ENDPOINT"
echo ""

check() {
  local label="$1"
  local url="$2"
  local status
  status=$(curl -sf -o /dev/null -w "%{http_code}" "$url" 2>/dev/null || echo "000")
  if [[ "$status" == "200" ]]; then
    echo "  ✓ $label ($status)"
  else
    echo "  ✗ $label ($status)"
    return 1
  fi
}

PASS=0
FAIL=0

check "GET /v1/health"  "$ENDPOINT/v1/health"  && ((PASS++)) || ((FAIL++))
check "GET /v1/status"  "$ENDPOINT/v1/status"  && ((PASS++)) || ((FAIL++)) || true
check "GET /v1/openapi.json" "$ENDPOINT/v1/openapi.json" && ((PASS++)) || ((FAIL++)) || true

echo ""
echo "  $PASS passed, $FAIL failed"

if [[ $FAIL -gt 0 ]]; then
  echo ""
  echo "  Some checks failed. Inspect logs on the API Linode:"
  echo "    journalctl -u omem-api.service -n 50"
  exit 1
fi

echo "==> All health checks passed."
