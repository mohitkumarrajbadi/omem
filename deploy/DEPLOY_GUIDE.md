# OMem Deployment Guide — Linode (Akamai Cloud)

Three paths from your laptop to a live OMem endpoint in the cloud.

---

## Path 1 — Test Locally with Docker (Start Here)

No credentials. No cloud. Works right now.

```bash
# 1. Build and start
docker compose -f deploy/docker/docker-compose.local.yml up --build

# 2. Verify (in a new terminal)
curl http://localhost:8080/v1/health

# 3. Store a memory
curl -X POST http://localhost:8080/v1/remember \
  -H 'Content-Type: application/json' \
  -d '{"content":"FastAPI uses Pydantic v2","session_id":"test","importance":0.9}'

# 4. Recall
curl -X POST http://localhost:8080/v1/recall \
  -H 'Content-Type: application/json' \
  -d '{"query":"Pydantic","session_id":"test","k":3}'

# 5. Explain (show why it was recalled)
curl -X POST http://localhost:8080/v1/explain \
  -H 'Content-Type: application/json' \
  -d '{"query":"Pydantic","session_id":"test","k":3}'

# 6. Save state
curl -X POST http://localhost:8080/v1/state/save \
  -H 'Content-Type: application/json' \
  -d '{"session_id":"test","goal":"Ship OMem v2","plan":["Design","Build","Test","Deploy"]}'

# 7. Snapshot
curl -X POST http://localhost:8080/v1/state/test/snapshot \
  -H 'Content-Type: application/json' \
  -d '{"label":"v2-kickoff"}'

# 8. Build LLM context
curl -X POST http://localhost:8080/v1/context/build \
  -H 'Content-Type: application/json' \
  -d '{"task":"implement auth middleware","session_id":"test","budget_tokens":4000}'
```

### Connect Claude Desktop to local Docker

Add to `~/Library/Application\ Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "omem-local": {
      "command": "curl",
      "args": ["-s", "-X", "POST", "http://localhost:8080/mcp/messages",
               "-H", "Content-Type: application/json", "-d", "@-"]
    }
  }
}
```

Or using the SSE transport:

```json
{
  "mcpServers": {
    "omem-local": {
      "transport": "sse",
      "url": "http://localhost:8080/mcp/sse",
      "timeout": 30000
    }
  }
}
```

Restart Claude Desktop. You should see OMem tools: `remember`, `recall`, `explain`,
`save_state`, `snapshot`, `rollback`, `checkpoint`, `build_context`, `learn`, `status`.

---

## Path 1b — Local Cloud Stack (Docker + Postgres)

**Use this before Linode.** Same `Dockerfile.cloud` and Postgres backend as the Akamai tech preview.

```bash
# One-time setup
cp .env.cloud.example .env.cloud

# Start API + Postgres (builds on first run, ~2–3 min)
./deploy/scripts/cloud-docker-up.sh -d

# Wait for healthy, then smoke test
./deploy/scripts/cloud-docker-smoke.sh

# Stop when done
./deploy/scripts/cloud-docker-down.sh
```

| Service | URL |
|---------|-----|
| Health | http://localhost:8080/v1/health |
| API docs | http://localhost:8080/docs |
| MCP SSE | http://localhost:8080/mcp/sse |

**Architecture (local):**

```text
localhost:8080 → omem-api (Dockerfile.cloud) → Postgres container
                      └── SQLite sidecars in /data (state, audit, runtime)
```

Optional worker profile (stub until `omem.cloud.worker` ships):

```bash
docker compose -f deploy/docker/docker-compose.cloud.yml --profile worker up -d
```

**Promote to Linode:** once local smoke passes, deploy the same `cloud` branch with
`./deploy/scripts/cloud-proof-deploy.sh` (Tier A SQLite) or Terraform + Postgres (Tier C).

---

## Path 2 — Single Linode VM (Fastest Cloud Deploy)

**Cost: ~$12/month** on a Linode 2GB shared instance.
**Time: under 15 minutes** once you have a token.

### Prerequisites

1. Get a Linode personal access token:
   - Log in at https://cloud.linode.com
   - Profile → API Tokens → Create Personal Access Token
   - Scopes: Linodes (Read/Write), StackScripts (Read/Write)

2. Install Linode CLI:
   ```bash
   pip install linode-cli
   linode-cli configure  # enter your token
   ```

### Deploy in 4 commands

```bash
# 1. Create the Linode (2GB, Ubuntu 22.04, Dallas DC)
linode-cli linodes create \
  --label omem-api \
  --region us-central \
  --type g6-standard-1 \
  --image linode/ubuntu22.04 \
  --root_pass "$(openssl rand -base64 24)" \
  --booted true

# 2. Get the IP
OMEM_IP=$(linode-cli linodes list --label omem-api --json | python3 -c "
import json,sys; data=json.load(sys.stdin); print(data[0]['ipv4'][0])")
echo "Your Linode IP: $OMEM_IP"

# 3. Wait for boot (~60 seconds), then run the setup script
sleep 60
ssh -o StrictHostKeyChecking=no root@$OMEM_IP bash < deploy/scripts/linode-setup.sh

# 4. Deploy OMem
ssh root@$OMEM_IP bash < deploy/scripts/linode-deploy-app.sh

# Done!
curl http://$OMEM_IP:8080/v1/health
```

### Setup script (deploy/scripts/linode-setup.sh)

```bash
#!/usr/bin/env bash
set -euo pipefail

apt-get update -qq
apt-get install -y python3-pip python3-venv docker.io docker-compose-plugin curl ufw

# Firewall: allow SSH + port 8080
ufw allow 22/tcp
ufw allow 8080/tcp
ufw --force enable

# Start Docker
systemctl enable --now docker

echo "Setup complete"
```

### App deploy script (deploy/scripts/linode-deploy-app.sh)

```bash
#!/usr/bin/env bash
set -euo pipefail

# Pull and run OMem from the published image
# (or build from source if deploying from git)
docker run -d \
  --name omem-api \
  --restart unless-stopped \
  -p 8080:8080 \
  -v omem-data:/data \
  -e OMEM_BACKEND=sqlite \
  -e OMEM_DB_PATH=/data/omem.db \
  -e OMEM_LOG_LEVEL=INFO \
  ghcr.io/mohitkumarrajbadi/omem:latest \
  uvicorn omem.cloud.server:app --host 0.0.0.0 --port 8080

echo "OMem is running at http://$(curl -s ifconfig.me):8080"
```

---

## Path 3 — Full Terraform Stack (Production)

Creates: API node + Worker node + DBaaS PostgreSQL + Object Storage + VLAN + Firewall.

### Prerequisites

```bash
# Install Terraform
brew install terraform            # macOS
# or: https://developer.hashicorp.com/terraform/install

export LINODE_TOKEN="your_personal_access_token"
```

### Deploy

```bash
cd deploy/linode/terraform
terraform init
terraform plan
terraform apply

# Get the API IP
terraform output api_ip
```

### What gets created

| Resource | Type | Monthly cost |
|---|---|---|
| `omem-preview-api` | Linode 4GB | ~$24 |
| `omem-preview-worker` | Linode 2GB | ~$12 |
| `omem-preview-db` | DBaaS PostgreSQL | ~$100 |
| `omem-preview-snapshots` | Object Storage | ~$5 |
| VPN + Firewall | Included | $0 |
| **Total** | | **~$141/month** |

### Teardown (important — avoids unexpected costs)

```bash
cd deploy/linode/terraform
terraform destroy
# or:
./deploy/scripts/teardown.sh --confirm
```

---

## Connecting AI Agents to the Deployed API

### Claude Desktop (any deployment)

```json
{
  "mcpServers": {
    "omem": {
      "transport": "sse",
      "url": "http://YOUR_IP:8080/mcp/sse"
    }
  }
}
```

### Cursor IDE MCP

In Cursor Settings → MCP:
```
Name: omem
Transport: SSE
URL: http://YOUR_IP:8080/mcp/sse
```

### Python SDK pointing to deployed instance

```python
from omem import AgentState

# Cloud mode: set env vars once
import os
os.environ["OMEM_ENDPOINT"] = "http://YOUR_IP:8080"
os.environ["OMEM_API_KEY"]  = "your_key_if_set"

agent = AgentState(session_id="my-agent")
agent.remember("FastAPI uses Pydantic v2", importance=0.9)
memories = agent.recall("Pydantic", k=5)
```

### Direct HTTP (any language)

```bash
BASE="http://YOUR_IP:8080"

# Remember
curl -X POST $BASE/v1/remember \
  -H 'Content-Type: application/json' \
  -d '{"content":"FastAPI uses Pydantic v2","session_id":"bot-1","importance":0.9}'

# Recall
curl -X POST $BASE/v1/recall \
  -H 'Content-Type: application/json' \
  -d '{"query":"Pydantic","session_id":"bot-1","k":5}'

# State snapshot
curl -X POST $BASE/v1/state/bot-1/snapshot \
  -H 'Content-Type: application/json' \
  -d '{"label":"before-deploy"}'

# Run STATE-Bench against your deployed instance
BASE_URL=$BASE python3 benchmarks/state_bench.py
```

---

## API Reference (Quick Summary)

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/v1/health` | Liveness probe |
| POST | `/v1/remember` | Store memory |
| POST | `/v1/recall` | Retrieve memories |
| POST | `/v1/explain` | Explain recall (score breakdown) |
| POST | `/v1/state/save` | Save goal + plan |
| GET | `/v1/state/{id}` | Load session state |
| POST | `/v1/state/{id}/snapshot` | Create snapshot |
| POST | `/v1/state/{id}/rollback` | Rollback to snapshot |
| POST | `/v1/state/{id}/fork` | Fork session |
| POST | `/v1/state/{id}/checkpoint` | Write crash checkpoint |
| POST | `/v1/state/{id}/resume` | Resume from checkpoint |
| GET | `/v1/state/{id}/status` | Full dashboard |
| POST | `/v1/context/build` | Build LLM context |
| POST | `/v1/knowledge/link` | Assert knowledge edge |
| GET | `/v1/observe/metrics` | Observability metrics |
| POST | `/v1/runtime/register` | Register agent |
| GET | `/mcp/sse` | MCP SSE stream |
| POST | `/mcp/messages` | MCP JSON-RPC |
| GET | `/docs` | Interactive Swagger UI |

---

## Securing the API

```bash
# Set an API key (any string)
docker run ... -e OMEM_API_KEY=omem_sk_$(openssl rand -hex 16) omem-local

# Use it in requests
curl -H "X-API-Key: omem_sk_..." http://YOUR_IP:8080/v1/recall ...

# Or as Bearer token
curl -H "Authorization: Bearer omem_sk_..." ...
```

---

## Updating

```bash
# Redeploy latest code
git pull
docker compose -f deploy/docker/docker-compose.local.yml up --build -d

# On Linode (single VM)
ssh root@$OMEM_IP "docker pull ghcr.io/mohitkumarrajbadi/omem:latest && \
  docker restart omem-api"
```
