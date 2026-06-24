#!/usr/bin/env bash
# provision.sh — create all Linode resources for the OMem Cloud tech preview.
#
# Usage:
#   export LINODE_TOKEN=<your-token>
#   export OMEM_PREVIEW_DOMAIN=state-preview.akamai.ai   # optional
#   ./deploy/scripts/provision.sh
#
# Requires: terraform >= 1.5, linode-cli (for DBaaS + Object Storage)
# See: docs/roadmap/AKAMAI_LINODE_DEPLOYMENT.md

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TERRAFORM_DIR="$SCRIPT_DIR/../linode/terraform"
LOG="$SCRIPT_DIR/provision.log"

: "${LINODE_TOKEN:?LINODE_TOKEN must be set}"
PREVIEW_DOMAIN="${OMEM_PREVIEW_DOMAIN:-state-preview.akamai.ai}"

echo "==> OMem Cloud Provision — $(date)" | tee "$LOG"
echo "    Domain : $PREVIEW_DOMAIN"
echo "    Region : us-east (default — set TF_VAR_region to override)"
echo ""

# ── 1. Terraform init + apply ──────────────────────────────────────────────
echo "==> Initialising Terraform..." | tee -a "$LOG"
cd "$TERRAFORM_DIR"
terraform init -input=false 2>&1 | tee -a "$LOG"

echo "==> Applying Terraform plan..." | tee -a "$LOG"
terraform apply -auto-approve \
  -var="linode_token=$LINODE_TOKEN" \
  -var="domain=$PREVIEW_DOMAIN" \
  2>&1 | tee -a "$LOG"

# ── 2. Capture outputs ─────────────────────────────────────────────────────
API_IP=$(terraform output -raw api_ip 2>/dev/null || echo "")
WORKER_IP=$(terraform output -raw worker_ip 2>/dev/null || echo "")
DB_HOST=$(terraform output -raw db_host 2>/dev/null || echo "")
OBJ_BUCKET=$(terraform output -raw obj_bucket 2>/dev/null || echo "")

echo ""
echo "==> Infrastructure provisioned:" | tee -a "$LOG"
echo "    API IP      : $API_IP"
echo "    Worker IP   : $WORKER_IP"
echo "    DB host     : $DB_HOST"
echo "    OBJ bucket  : $OBJ_BUCKET"
echo ""
echo "==> Next: run ./deploy/scripts/deploy.sh to install the application."
