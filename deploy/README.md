# OMem Deployment

Infrastructure for the **Akamai Agent State Cloud** tech preview on Linode.

Full details: [AKAMAI_LINODE_DEPLOYMENT.md](../docs/roadmap/AKAMAI_LINODE_DEPLOYMENT.md)

## Directory layout

```text
deploy/
├── scripts/         # One-command provision, deploy, teardown, health-check
├── docker/          # Dockerfile.cloud + docker-compose.cloud.yml
└── linode/
    └── terraform/   # Linode resource definitions (API, worker, DB, storage, VLAN)
```

## Quick start (Cloud Phase C4)

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
