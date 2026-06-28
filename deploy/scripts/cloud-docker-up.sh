#!/usr/bin/env bash
# cloud-docker-up.sh — Start OMem Cloud locally (Docker + Postgres).
#
# Mirrors Linode deployment; same Dockerfile.cloud used in production preview.
#
# Usage:
#   ./deploy/scripts/cloud-docker-up.sh          # foreground
#   ./deploy/scripts/cloud-docker-up.sh -d       # detached
#   ./deploy/scripts/cloud-docker-down.sh        # stop
#
# See: deploy/DEPLOY_GUIDE.md — Path 1b

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
COMPOSE_FILE="$ROOT/deploy/docker/docker-compose.cloud.yml"
ENV_FILE="$ROOT/.env.cloud"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "==> Creating $ENV_FILE from .env.cloud.example"
  cp "$ROOT/.env.cloud.example" "$ENV_FILE"
  echo ""
  echo "  IMPORTANT: Edit $ENV_FILE and set POSTGRES_PASSWORD before continuing."
  echo "  Then re-run this script."
  echo ""
fi

cd "$ROOT"
echo "==> Starting OMem Cloud (API + Postgres)..."
docker compose -f "$COMPOSE_FILE" up --build "$@"
