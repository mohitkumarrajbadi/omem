#!/usr/bin/env bash
# deploy.sh — install / update the OMem Cloud application on provisioned Linodes.
#
# Usage:
#   ./deploy/scripts/deploy.sh [--version v1.0.0]
#
# Requires: ssh access to API and Worker Linodes (key auth), ansible or cloud-init.
# See: docs/roadmap/AKAMAI_LINODE_DEPLOYMENT.md

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TERRAFORM_DIR="$SCRIPT_DIR/../linode/terraform"
VERSION="${OMEM_VERSION:-$(git -C "$SCRIPT_DIR/../.." describe --tags --always 2>/dev/null || echo dev)}"

while [[ $# -gt 0 ]]; do
  case $1 in
    --version) VERSION="$2"; shift 2 ;;
    *) echo "Unknown arg: $1"; exit 1 ;;
  esac
done

echo "==> Deploying OMem Cloud version: $VERSION"

# Resolve IPs from Terraform state
cd "$TERRAFORM_DIR"
API_IP=$(terraform output -raw api_ip 2>/dev/null)
WORKER_IP=$(terraform output -raw worker_ip 2>/dev/null)
DB_URL=$(terraform output -raw db_url 2>/dev/null)
OBJ_ENDPOINT=$(terraform output -raw obj_endpoint 2>/dev/null)
OBJ_BUCKET=$(terraform output -raw obj_bucket 2>/dev/null)

if [[ -z "$API_IP" ]]; then
  echo "ERROR: No API IP found. Run provision.sh first."
  exit 1
fi

SSH_OPTS="-o StrictHostKeyChecking=no -o ConnectTimeout=10"

deploy_node() {
  local ip="$1"
  local role="$2"
  echo "==> Deploying to $role ($ip)..."

  ssh $SSH_OPTS "root@$ip" bash -s << REMOTE
set -euo pipefail

# Install / upgrade omem
pip3 install --quiet --upgrade "omem-os[fast,embeddings,postgres]==$VERSION" 2>/dev/null \
  || pip3 install --quiet --upgrade omem-os

# Write environment file
cat > /etc/omem.env << ENV
OMEM_CLOUD_MODE=1
OMEM_BACKEND=postgres
OMEM_DB_URL=$DB_URL
OMEM_OBJ_STORAGE_ENDPOINT=$OBJ_ENDPOINT
OMEM_OBJ_STORAGE_BUCKET=$OBJ_BUCKET
OMEM_LOG_LEVEL=INFO
ENV

# Restart service
systemctl daemon-reload
systemctl restart omem-${role}.service || true

echo "  $role OK"
REMOTE
}

deploy_node "$API_IP" "api"
deploy_node "$WORKER_IP" "worker"

echo ""
echo "==> Deploy complete. Run ./deploy/scripts/health-check.sh to verify."
