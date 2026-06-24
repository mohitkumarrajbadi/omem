terraform {
  required_version = ">= 1.5"

  required_providers {
    linode = {
      source  = "linode/linode"
      version = "~> 2.0"
    }
  }
}

provider "linode" {
  token = var.linode_token
}

# ── VLAN — private network between API and DB ──────────────────────────────
resource "linode_vlan" "omem_preview" {
  label  = "omem-preview-vlan"
  region = var.region
}

# ── API Linode — public-facing FastAPI service ─────────────────────────────
resource "linode_instance" "api" {
  label  = "omem-preview-api"
  region = var.region
  type   = "g6-standard-2"   # Shared 4GB

  image     = "linode/debian12"
  root_pass = random_password.root.result

  authorized_keys = var.ssh_key != "" ? [var.ssh_key] : []

  interface {
    purpose = "public"
  }

  interface {
    purpose  = "vlan"
    label    = linode_vlan.omem_preview.label
    ipam_address = "10.0.0.2/24"
  }

  tags = ["omem-preview", "api"]

  lifecycle {
    ignore_changes = [root_pass]
  }
}

# ── Worker Linode — background jobs (sleep cycles, retention, archival) ────
resource "linode_instance" "worker" {
  label  = "omem-preview-worker"
  region = var.region
  type   = "g6-standard-1"   # Shared 2GB

  image     = "linode/debian12"
  root_pass = random_password.root.result

  authorized_keys = var.ssh_key != "" ? [var.ssh_key] : []

  interface {
    purpose      = "vlan"
    label        = linode_vlan.omem_preview.label
    ipam_address = "10.0.0.3/24"
  }

  tags = ["omem-preview", "worker"]

  lifecycle {
    ignore_changes = [root_pass]
  }
}

resource "random_password" "root" {
  length  = 32
  special = true
}

# ── Firewall — only API node is reachable from internet ───────────────────
resource "linode_firewall" "omem_preview" {
  label = "omem-preview-firewall"

  inbound_policy  = "DROP"
  outbound_policy = "ACCEPT"

  inbound {
    label    = "allow-https"
    action   = "ACCEPT"
    protocol = "TCP"
    ports    = "443"
    ipv4     = ["0.0.0.0/0"]
    ipv6     = ["::/0"]
  }

  inbound {
    label    = "allow-ssh-admin"
    action   = "ACCEPT"
    protocol = "TCP"
    ports    = "22"
    # Restrict to Akamai VPN / office IP range in production
    ipv4 = ["0.0.0.0/0"]
  }

  linodes = [linode_instance.api.id]
}
