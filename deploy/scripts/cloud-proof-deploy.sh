#!/usr/bin/env bash
# cloud-proof-deploy.sh — Deploy the `cloud` branch to a Linode VM for Akamai demos.
#
# Usage (from repo root):
#   export OMEM_LINODE_IP=203.0.113.10
#   ./deploy/scripts/cloud-proof-deploy.sh
#
#   ./deploy/scripts/cloud-proof-deploy.sh --host 203.0.113.10 --branch cloud --api-key omem_sk_demo
#
# First-time VM bootstrap:
#   ssh root@$OMEM_LINODE_IP 'bash -s' < deploy/scripts/linode-setup.sh
#
# See: docs/guides/CLOUD_PROOF.md

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

HOST="${OMEM_LINODE_IP:-}"
BRANCH="${OMEM_BRANCH:-cloud}"
API_KEY="${OMEM_API_KEY:-}"
PORT="${OMEM_PORT:-8080}"
USER="${OMEM_SSH_USER:-root}"
SKIP_SETUP=false

usage() {
  sed -n '2,12p' "$0" | sed 's/^# \?//'
  exit "${1:-0}"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --host) HOST="$2"; shift 2 ;;
    --branch) BRANCH="$2"; shift 2 ;;
    --api-key) API_KEY="$2"; shift 2 ;;
    --port) PORT="$2"; shift 2 ;;
    --user) USER="$2"; shift 2 ;;
    --skip-setup) SKIP_SETUP=true; shift ;;
    -h|--help) usage 0 ;;
    *) echo "Unknown option: $1"; usage 1 ;;
  esac
done

if [[ -z "$HOST" ]]; then
  echo "ERROR: set OMEM_LINODE_IP or pass --host <ip>"
  exit 1
fi

echo "==> OMem Cloud Proof Deploy"
echo "    host:   ${USER}@${HOST}"
echo "    branch: ${BRANCH}"
echo "    port:   ${PORT}"
echo ""

if [[ "$SKIP_SETUP" != true ]]; then
  echo "==> Checking SSH connectivity..."
  ssh -o ConnectTimeout=10 -o StrictHostKeyChecking=accept-new "${USER}@${HOST}" "echo ok" >/dev/null
fi

echo "==> Deploying via linode-deploy-app.sh (branch=${BRANCH})..."
ssh "${USER}@${HOST}" \
  OMEM_BRANCH="$BRANCH" \
  OMEM_API_KEY="$API_KEY" \
  OMEM_PORT="$PORT" \
  'bash -s' < "$SCRIPT_DIR/linode-deploy-app.sh"

PUBLIC_IP="$HOST"
echo ""
echo "=============================================="
echo "  OMem Cloud Proof — LIVE"
echo "=============================================="
echo "  Health:   http://${PUBLIC_IP}:${PORT}/v1/health"
echo "  API docs: http://${PUBLIC_IP}:${PORT}/docs"
echo "  MCP SSE:  http://${PUBLIC_IP}:${PORT}/mcp/sse"
echo ""
echo "  Demo script: docs/guides/CLOUD_PROOF.md"
echo "=============================================="

if [[ -n "$API_KEY" ]]; then
  echo ""
  echo "  export OMEM_ENDPOINT=http://${PUBLIC_IP}:${PORT}"
  echo "  export OMEM_API_KEY=${API_KEY}"
fi
