# OMem Deployment

Infrastructure for the **Akamai Agent State Cloud** tech preview on Linode.

> **Cloud stack note:** Docker Compose files and cloud service entrypoints that
> invoke `omem.cloud.*` live in the sibling **`omem-cloud`** repository. This
> OSS repo ships local SQLite/Postgres backends only; install `omem-cloud`
> separately for managed API deployment.

Full details: [AKAMAI_LINODE_DEPLOYMENT.md](../docs/roadmap/AKAMAI_LINODE_DEPLOYMENT.md)

## Directory layout

```text
deploy/
├── scripts/         # One-command provision, deploy, teardown, health-check
├── docker/          # Dockerfile.local, Dockerfile.cloud, compose files
└── linode/
    └── terraform/   # Linode resource definitions (API, worker, DB, storage, VLAN)
```

## Quick start (local Docker)

```bash
docker compose -f deploy/docker/docker-compose.local.yml up --build
```

## Quick start (Akamai cloud proof on Linode)

Deploy the **`cloud`** branch to a Linode VM for wizard / leadership demos:

```bash
export OMEM_LINODE_IP=<your-linode-ip>
ssh root@$OMEM_LINODE_IP 'bash -s' < deploy/scripts/linode-setup.sh   # first time only
./deploy/scripts/cloud-proof-deploy.sh --host "$OMEM_LINODE_IP" --branch cloud
```

Playbook: [docs/guides/CLOUD_PROOF.md](../docs/guides/CLOUD_PROOF.md)

## Quick start (Cloud Phase C4 — full Terraform)

```bash
# 1. Set credentials
export LINODE_TOKEN=<your-token>
export OMEM_PREVIEW_DOMAIN=state-preview.akamai.ai

# 2. Provision all infrastructure (~5 min)
./deploy/scripts/provision.sh

# 3. Deploy application
./deploy/scripts/deploy.sh

# 4. Smoke test
./deploy/scripts/health-check.sh

# 5. Seed demo data for leadership demo
./deploy/scripts/seed-demo-data.sh

# 6. Teardown when done (automation compliance — short-lived resources)
./deploy/scripts/teardown.sh --confirm
```

## Resource budget

Uses ~5–6 of the 20-entity account limit:

| Entity | Spec | Role |
|--------|------|------|
| Linode 1 | Shared 4GB | API gateway + FastAPI |
| Linode 2 | Shared 2GB | Background worker |
| DBaaS PostgreSQL | Smallest plan | Multi-tenant state + memory |
| Object Storage | 1 bucket | Snapshot archives |
| VLAN | 1 | API ↔ DB private network |
