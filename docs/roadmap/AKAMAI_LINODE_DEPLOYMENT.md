# Akamai / Linode Deployment Plan

Infrastructure plan for **OMem Cloud tech preview** on Akamai employee Linode accounts. This document covers resource allocation, network topology, deployment artifacts, operations, and scaling path.

Related docs:

- [Full Implementation Plan](./FULL_IMPLEMENTATION_PLAN.md) — master engineering phases
- [V2 Architecture Vision](./V2_ARCHITECTURE.md) — platform shape

---

## Product Goal

Prove OMem as a managed **Agent State Cloud** that Akamai can sell:

```bash
pip install omem
export OMEM_ENDPOINT=https://state.akamai.ai
export OMEM_API_KEY=omem_sk_...
```

Customer runs agents. Akamai runs memory, state, context, snapshots, and observability. No customer-managed Postgres, vector DB, Redis, or graph DB.

---

## Account Constraints

Default Akamai employee Linode account limits:

| Limit | Value | Implication |
|-------|-------|-------------|
| Max entities | 20 | Each DBaaS, volume, LKE node, Linode counts as 1 |
| Max IPv4 per compute | 1 | Public IP on API gateway only; worker on VLAN |
| Max compute plan | Shared 16GB / Dedicated 8GB | API gets 4GB shared; worker gets 2GB |
| Object Storage | 5 TB per cluster | Plenty for snapshots and audit archives |
| Max objects | 50,000,000 | Snapshot JSON + gzip archives |
| Max buckets | 1,000 | 1 bucket for preview |
| Max block volume | 10 TB | Optional FAISS index cache |
| VLAN limit | 10 | 1 VLAN for preview |

**Automation rule:** Assume all resources are **short-lived**. Every provision script must have a matching teardown script.

**Scale beyond limits:** [Compute Capacity Intake](https://collaborate.akamai.com/confluence/display/ETG/Compute+Capacity+Intake) form.

---

## Preview Architecture (Lean — 5–6 Entities)

Skip LKE for the tech preview. Two Linodes + managed DB + Object Storage is easier to demo, debug, and tear down.

```text
                         Internet
                             │
                             ▼
              ┌──────────────────────────┐
              │  Linode 1 — API Gateway   │
              │  Shared 4GB               │
              │  ─────────────────────    │
              │  Caddy (TLS termination)  │
              │  FastAPI (omem/cloud/)    │
              │  Public IPv4              │
              └────────────┬─────────────┘
                           │ VLAN (private)
              ┌────────────┴─────────────┐
              │                          │
              ▼                          ▼
┌─────────────────────┐    ┌─────────────────────────┐
│ Linode 2 — Worker    │    │ DBaaS PostgreSQL         │
│ Shared 2GB           │    │ Smallest plan            │
│ ─────────────────    │    │ Multi-tenant state +     │
│ Sleep cycles         │    │ memory metadata          │
│ Retention jobs       │    │ Private connection     │
│ Snapshot archival    │    └─────────────────────────┘
└──────────┬───────────┘
           │
           ▼
┌─────────────────────────┐
│ Object Storage (1 bucket)│
│ ─────────────────────── │
│ Snapshot archives (.gz)  │
│ Audit log exports        │
│ Large memory exports     │
└─────────────────────────┘
```

### Entity budget

| # | Entity | Spec | Role |
|---|--------|------|------|
| 1 | Linode — API | Shared 4GB, 80GB disk | Gateway + FastAPI state API |
| 2 | Linode — Worker | Shared 2GB, 50GB disk | Background jobs |
| 3 | DBaaS PostgreSQL | Smallest available | Primary data store |
| 4 | Object Storage bucket | `omem-preview-snapshots` | Snapshot + audit archives |
| 5 | VLAN | `omem-preview-vlan` | API ↔ DB private network |
| 6 | Block Volume (optional) | 50GB | FAISS index cache on API node |

**Total: 5–6 of 20 entities** — leaves headroom for staging or a dashboard node.

---

## Alternative: Single-Node Preview (3 Entities)

For fastest proof with minimum footprint:

| # | Entity | Role |
|---|--------|------|
| 1 | Linode Shared 8GB | API + worker combined |
| 2 | DBaaS PostgreSQL | Data store |
| 3 | Object Storage bucket | Snapshots |

Use this for initial dogfooding before splitting API and worker.

---

## Network & Security

### VLAN layout

```text
Public subnet:   API Linode (443/tcp inbound)
Private subnet:  API ↔ DBaaS ↔ Worker (VLAN)
No public IP:    Worker, DBaaS
```

### TLS

- Caddy on API Linode with automatic Let's Encrypt
- Preview URL: `https://state-preview.akamai.ai` (or Linode IP until DNS is ready)
- Force HTTPS redirect

### Firewall rules (API Linode)

| Direction | Port | Source | Purpose |
|-----------|------|--------|---------|
| Inbound | 443 | 0.0.0.0/0 | HTTPS API |
| Inbound | 22 | Akamai VPN / office IP | SSH admin |
| Outbound | 5432 | VLAN | Postgres |
| Outbound | 443 | Object Storage endpoint | Snapshot upload |

### Authentication

```text
Header:  Authorization: Bearer omem_sk_{org}_{random}
Format:  omem_sk_acme_a1b2c3d4e5f6...
Storage: SHA-256 hash in api_keys table
Scopes:  read | write | admin
```

Every request gets a `X-Request-ID` header in the response.

---

## Service Components

### API Gateway (Linode 1)

| Component | Technology |
|-----------|------------|
| Reverse proxy | Caddy 2 |
| Application | FastAPI (`omem/cloud/server.py`) |
| Process manager | systemd |
| Container (optional) | Docker via `Dockerfile.cloud` |

Environment:

```bash
OMEM_CLOUD_MODE=1
OMEM_BACKEND=postgres
OMEM_DB_URL=postgresql://...@db-private:5432/omem
OMEM_OBJ_STORAGE_ENDPOINT=https://...
OMEM_OBJ_STORAGE_BUCKET=omem-preview-snapshots
OMEM_OBJ_STORAGE_KEY=...
OMEM_LOG_LEVEL=INFO
```

### Worker (Linode 2)

Background jobs:

| Job | Schedule | Purpose |
|-----|----------|---------|
| Sleep cycle | Per-namespace, configurable | Memory consolidation |
| Retention enforcement | Daily | Governance policies |
| Snapshot archival | On snapshot create | Upload to Object Storage |
| Audit export | Weekly | Compliance archive |
| Health heartbeat | 60s | Ops monitoring |

Same codebase, different systemd unit: `omem-worker.service`.

### Database (DBaaS PostgreSQL)

Schemas:

```text
public/
├── memories              (existing, + org_id column)
├── state_sessions
├── state_snapshots
├── state_checkpoints
├── state_fork_lineage
├── organizations
├── teams
├── api_keys
├── audit_events
└── trace_events
```

Connection pooling: SQLAlchemy pool size 5 on API, 2 on worker.

Backups: DBaaS managed daily backups (enable on provision).

### Object Storage

Bucket structure:

```text
omem-preview-snapshots/
├── org/{org_id}/
│   ├── snapshots/{snapshot_id}.json.gz
│   ├── exports/{export_id}.json
│   └── audit/{date}.jsonl.gz
└── system/
    └── health/{timestamp}.json
```

Lifecycle policy: delete objects older than 30 days (preview tier).

---

## Deployment Artifacts (Repo Layout)

```text
deploy/
├── linode/
│   ├── terraform/
│   │   ├── main.tf              # Provider + variables
│   │   ├── api.tf               # API Linode
│   │   ├── worker.tf            # Worker Linode
│   │   ├── database.tf          # DBaaS PostgreSQL
│   │   ├── object_storage.tf    # Bucket + keys
│   │   ├── vlan.tf              # Private network
│   │   ├── firewall.tf          # Cloud firewall rules
│   │   ├── variables.tf
│   │   └── outputs.tf           # Endpoint URL, DB connection
│   ├── ansible/
│   │   ├── inventory.yml
│   │   ├── api.yml              # Caddy + FastAPI + systemd
│   │   ├── worker.yml           # Worker service
│   │   └── common.yml           # Python, omem install, env file
│   └── cloud-init/
│       ├── api.yaml
│       └── worker.yaml
├── docker/
│   ├── Dockerfile.cloud
│   └── docker-compose.cloud.yml
└── scripts/
    ├── provision.sh             # One-command provision
    ├── deploy.sh                # Push new version
    ├── teardown.sh              # Destroy all resources
    ├── health-check.sh          # Smoke test against endpoint
    └── seed-demo-data.sh        # Demo org + sample agent state
```

### Provision workflow

```bash
# 1. Set credentials
export LINODE_TOKEN=...
export OMEM_PREVIEW_DOMAIN=state-preview.akamai.ai

# 2. Provision infrastructure
./deploy/scripts/provision.sh

# 3. Deploy application
./deploy/scripts/deploy.sh --version $(git describe --tags)

# 4. Smoke test
./deploy/scripts/health-check.sh https://state-preview.akamai.ai

# 5. Seed demo data for leadership demo
./deploy/scripts/seed-demo-data.sh
```

### Teardown workflow

```bash
./deploy/scripts/teardown.sh --confirm
```

Required for automation compliance (short-lived resources).

---

## Cloud API Endpoints (Deployed Service)

Base URL: `https://state-preview.akamai.ai/v1`

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/health` | None | Liveness probe |
| GET | `/status` | None | Version, uptime, dependency status |
| POST | `/memory/remember` | Bearer | Store memory |
| POST | `/memory/recall` | Bearer | Hybrid retrieval |
| GET | `/memory/stats` | Bearer | Namespace stats |
| POST | `/state/save` | Bearer | Save session state |
| GET | `/state/{session_id}` | Bearer | Load session state |
| POST | `/state/snapshot` | Bearer | Create snapshot |
| POST | `/state/rollback` | Bearer | Rollback to snapshot |
| POST | `/state/fork` | Bearer | Fork from snapshot |
| POST | `/state/checkpoint` | Bearer | Lightweight checkpoint |
| POST | `/state/resume` | Bearer | Resume from checkpoint |
| POST | `/context/build` | Bearer | Build optimal context |
| GET | `/observe/metrics` | Bearer | Org metrics |
| GET | `/observe/traces/{session_id}` | Bearer | Session traces |

OpenAPI spec: `GET /v1/openapi.json`

---

## Multi-Tenancy on Preview

### Org isolation

Every database row includes `org_id`. Middleware extracts org from API key and rejects cross-org access.

### Namespace mapping

```text
API key scoped to org "acme":
  Allowed namespaces:
    org/acme/*
    org/acme/team/*
    personal/*  (if key has personal scope)

API key scoped to team "platform" in org "acme":
  Allowed namespaces:
    org/acme/team/platform/*
```

### API key provisioning (internal preview)

Manual for preview; self-serve portal in Enterprise Phase E4.

```bash
# Admin CLI on API server
omem-cloud keys create --org acme --scopes read,write --expires 90d
# → omem_sk_acme_x7y8z9...
```

---

## Operations Checklist

### Day 0 (Launch)

- [ ] TLS certificate active
- [ ] DBaaS backups enabled
- [ ] Object Storage lifecycle policy set (30-day retention)
- [ ] Firewall rules applied
- [ ] Health check passing (`/v1/health`)
- [ ] Demo data seeded
- [ ] Internal DNS or IP documented
- [ ] Teardown script tested

### Day 1–30 (Preview)

- [ ] Monitor API latency (target p99 < 500ms for recall)
- [ ] Monitor DB connection pool utilization
- [ ] Monitor Object Storage growth
- [ ] Weekly audit export to Object Storage
- [ ] Collect pilot feedback
- [ ] Track preview success metrics (see below)

### Incident response (preview SLA: best-effort)

| Severity | Response | Action |
|----------|----------|--------|
| API down | 4 hours | Restart service, check DB connectivity |
| Data loss | Immediate | Restore from DBaaS backup |
| Key compromise | 1 hour | Revoke key, rotate, audit access log |

---

## Preview Success Metrics

| Metric | Target | How measured |
|--------|--------|--------------|
| Pilot teams onboarded | 3–5 | API key count |
| Agent sessions with checkpoint/resume | 50+ | `state_checkpoints` table |
| Context token savings | >40% avg | `observe.metrics()` |
| State restore success rate | >99% | restore attempts vs failures |
| API uptime | >99% | health check monitoring |
| Recall p99 latency | <500ms | trace events |

---

## Scaling Path

### Preview → Beta (within 20-entity limit)

Add without LKE:

| Addition | Entities | Purpose |
|----------|----------|---------|
| Staging Linode (4GB) | +1 | Pre-production testing |
| Dashboard Linode (2GB) | +1 | Public metrics UI |
| Read replica DBaaS | +1 | Read-heavy recall |

### Beta → Production (requires Capacity Intake)

| Addition | Purpose |
|----------|---------|
| LKE cluster (3 nodes) | Horizontal API scaling |
| Second region | Multi-region state |
| Dedicated 8GB nodes | Production workloads |
| Additional DBaaS | HA failover |
| Akamai CDN / edge | TLS + DDoS + edge caching |

### Edge integration (Enterprise E3)

```text
Agent request
    │
    ▼
Akamai Edge (policy check, rate limit, cache hot context)
    │
    ▼
Nearest OMem Cloud region (state API)
    │
    ▼
Postgres + Object Storage
```

This is the long-term moat: state-aware edge routing that AWS/GCP do not offer as a unified product.

---

## Cost Estimate (Preview)

Approximate monthly cost on employee Linode account (free to employee, useful for business case):

| Resource | Est. cost |
|----------|-----------|
| Linode 4GB shared | ~$24/mo |
| Linode 2GB shared | ~$12/mo |
| DBaaS PostgreSQL (smallest) | ~$15/mo |
| Object Storage (<100GB) | ~$5/mo |
| **Total preview** | **~$56/mo** |

Teardown when not actively demoing to stay within automation guidelines.

---

## SDK Integration (Client Side)

After deployment, developers connect with zero code change:

```python
from omem import AgentState

# Auto-detects OMEM_ENDPOINT and OMEM_API_KEY from environment
agent = AgentState(session_id="my-coding-agent")

agent.memory.remember("Project uses FastAPI", namespace="org/acme/team/platform")
agent.state.set_goal("Add OAuth2 middleware")
checkpoint = agent.state.checkpoint()

# Later, after crash:
agent.state.resume(checkpoint)
context = agent.context.build(task="continue OAuth work", budget_tokens=6000)
```

MCP config for Cursor / Claude Desktop:

```json
{
  "mcpServers": {
    "omem": {
      "command": "omem",
      "args": ["serve", "--transport", "stdio"],
      "env": {
        "OMEM_ENDPOINT": "https://state-preview.akamai.ai",
        "OMEM_API_KEY": "omem_sk_acme_..."
      }
    }
  }
}
```

---

## Next Steps

1. Complete **Phase 2 (State Engine)** in OSS — required before cloud API is meaningful
2. Implement **Cloud C2 (FastAPI service)** locally with Docker
3. Create `deploy/scripts/provision.sh` and `teardown.sh`
4. Provision preview on Linode employee account
5. Run leadership demo script against live endpoint
6. Onboard 3 internal pilot teams

See [Full Implementation Plan](./FULL_IMPLEMENTATION_PLAN.md) for complete phase breakdown.
