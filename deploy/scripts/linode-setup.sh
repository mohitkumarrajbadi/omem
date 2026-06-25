#!/usr/bin/env bash
# linode-setup.sh — Bootstrap a fresh Linode (Ubuntu 22.04) for OMem.
# Run once via: ssh root@<IP> bash < deploy/scripts/linode-setup.sh
set -euo pipefail

echo "==> Updating system packages..."
apt-get update -qq
apt-get upgrade -y -qq

echo "==> Installing Docker, Python, utilities..."
apt-get install -y --no-install-recommends \
    python3-pip python3-venv \
    docker.io docker-compose-plugin \
    curl wget git ufw htop

echo "==> Configuring firewall..."
ufw allow 22/tcp
ufw allow 8080/tcp
ufw allow 443/tcp
ufw --force enable

echo "==> Starting Docker..."
systemctl enable --now docker

echo "==> Creating omem user and data directory..."
useradd -m -s /bin/bash omem 2>/dev/null || true
mkdir -p /data/omem
chown omem:omem /data/omem

echo "==> Setup complete. Ready for linode-deploy-app.sh"
