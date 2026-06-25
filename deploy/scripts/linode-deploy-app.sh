#!/usr/bin/env bash
# linode-deploy-app.sh — Deploy OMem from source on a Linode VM.
# Run via: ssh root@<IP> bash < deploy/scripts/linode-deploy-app.sh
set -euo pipefail

OMEM_REPO="${OMEM_REPO:-https://github.com/mohitkumarrajbadi/omem.git}"
OMEM_BRANCH="${OMEM_BRANCH:-cloud}"   # Akamai proof branch; override with OMEM_BRANCH=main if needed
OMEM_API_KEY="${OMEM_API_KEY:-}"   # optional: set env var before running
OMEM_PORT="${OMEM_PORT:-8080}"

echo "==> Cloning OMem repo..."
rm -rf /opt/omem
git clone --depth 1 -b "$OMEM_BRANCH" "$OMEM_REPO" /opt/omem

echo "==> Building Docker image..."
cd /opt/omem
docker build -f deploy/docker/Dockerfile.local -t omem-local:latest .

echo "==> Stopping old container (if any)..."
docker rm -f omem-api 2>/dev/null || true

echo "==> Starting OMem API..."
docker run -d \
  --name omem-api \
  --restart unless-stopped \
  -p "${OMEM_PORT}:8080" \
  -v omem-data:/data \
  -e OMEM_BACKEND=sqlite \
  -e OMEM_DB_PATH=/data/omem.db \
  -e OMEM_NAMESPACE=default \
  -e OMEM_LOG_LEVEL=INFO \
  -e OMEM_API_KEY="${OMEM_API_KEY}" \
  omem-local:latest

echo "==> Waiting for health check..."
sleep 8
for i in {1..10}; do
  if curl -sf "http://localhost:${OMEM_PORT}/v1/health" > /dev/null; then
    echo ""
    echo "==> OMem is LIVE at http://$(curl -s ifconfig.me):${OMEM_PORT}"
    echo "==> API Docs: http://$(curl -s ifconfig.me):${OMEM_PORT}/docs"
    echo "==> MCP SSE:  http://$(curl -s ifconfig.me):${OMEM_PORT}/mcp/sse"
    echo ""
    curl -s "http://localhost:${OMEM_PORT}/v1/health" | python3 -m json.tool
    exit 0
  fi
  echo "  waiting ($i/10)..."
  sleep 3
done

echo "ERROR: health check failed. Check logs:"
docker logs omem-api --tail 30
exit 1
