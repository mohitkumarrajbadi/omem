#!/usr/bin/env bash
# cloud-docker-down.sh — Stop local OMem Cloud Docker stack.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
docker compose -f "$ROOT/deploy/docker/docker-compose.cloud.yml" down "$@"
