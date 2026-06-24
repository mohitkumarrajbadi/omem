#!/usr/bin/env bash
# teardown.sh — destroy ALL Linode resources created by provision.sh.
#
# Required for automation compliance (short-lived resources policy).
#
# Usage:
#   ./deploy/scripts/teardown.sh --confirm
#
# See: docs/roadmap/AKAMAI_LINODE_DEPLOYMENT.md

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TERRAFORM_DIR="$SCRIPT_DIR/../linode/terraform"
LOG="$SCRIPT_DIR/teardown.log"

CONFIRMED=false
while [[ $# -gt 0 ]]; do
  case $1 in
    --confirm) CONFIRMED=true; shift ;;
    *) echo "Unknown arg: $1"; exit 1 ;;
  esac
done

if [[ "$CONFIRMED" != "true" ]]; then
  echo ""
  echo "  WARNING: This will destroy ALL OMem Cloud preview resources."
  echo "           Linodes, DBaaS instance, Object Storage bucket, and VLAN."
  echo ""
  echo "  Re-run with --confirm to proceed:"
  echo "    ./deploy/scripts/teardown.sh --confirm"
  echo ""
  exit 1
fi

echo "==> OMem Cloud Teardown — $(date)" | tee "$LOG"

cd "$TERRAFORM_DIR"
terraform destroy -auto-approve \
  -var="linode_token=${LINODE_TOKEN:?LINODE_TOKEN must be set}" \
  2>&1 | tee -a "$LOG"

echo ""
echo "==> All resources destroyed. Account is clean." | tee -a "$LOG"
