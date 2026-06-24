# Linode Terraform

Provisions the OMem Cloud tech preview on Akamai / Linode.

## Prerequisites

- Terraform >= 1.5
- Linode personal access token (set as `LINODE_TOKEN`)
- `linode-cli` installed (for debugging)

## Resources created

| Resource | Type | Role |
|----------|------|------|
| `omem-preview-api` | Linode Shared 4GB | API gateway + FastAPI |
| `omem-preview-worker` | Linode Shared 2GB | Background jobs |
| `omem-preview-db` | DBaaS PostgreSQL | Multi-tenant state |
| `omem-preview-snapshots` | Object Storage bucket | Snapshot archives |
| `omem-preview-vlan` | VLAN | Private API ↔ DB network |
| `omem-preview-firewall` | Firewall | Inbound rules |

**Total: 6 of 20 entity limit.**

## Usage

```bash
cd deploy/linode/terraform
terraform init
terraform plan -var="linode_token=$LINODE_TOKEN"
terraform apply -var="linode_token=$LINODE_TOKEN"
```

Or use the one-command scripts:

```bash
./deploy/scripts/provision.sh   # provision
./deploy/scripts/teardown.sh --confirm   # destroy all
```

## Teardown

Always run teardown when not actively using the preview — automation
compliance requires short-lived resources.
