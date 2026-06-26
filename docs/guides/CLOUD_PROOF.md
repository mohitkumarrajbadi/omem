# Cloud Proof Branch — Akamai / Linode Demo

Use this guide to prove **OMem as a managed Agent State service** on Akamai Cloud (Linode) for internal reviews, wizard competitions, and tech-preview conversations.

**Positioning:** *Akamai Agent State Cloud* — persistent memory, checkpoints, and context for AI agents, delivered as an HTTP + MCP endpoint.

---

## Branch model (proving state)

```text
feat/*  ──PR──►  dev  ──►  staging  ──►  main     (OSS releases)
                    │         │
                    └────┬────┘
                         ▼
                       cloud  ──deploy──►  Linode VM  (live demo URL)
```

| Branch | Role | Who uses it |
|--------|------|-------------|
| `dev` | Daily development; all feature PRs land here | Engineers |
| `staging` | Integration soak before release | Pre-release QA |
| `main` | Stable OSS releases (`v3.x` tags) | PyPI, public users |
| **`cloud`** | **Always deployable demo** for Akamai proof | You + demo audience |

### Rules for `cloud`

1. **`cloud` merges from `staging`** (preferred) or `dev` when you need a fast demo fix.
2. **Never develop directly on `cloud`** — merge only; keeps the demo reproducible.
3. **Every push to `cloud` should be deployable** — CI runs tests + Docker build.
4. **Tag demo milestones:** `cloud-preview-2026-06-25` on `cloud` before big presentations.

---

## One-time setup

### 1. Create the four branches on GitHub

```bash
git checkout main
git pull origin main

git checkout -b dev && git push -u origin dev
git checkout -b staging && git push -u origin staging
git checkout -b cloud && git push -u origin cloud

git checkout dev   # return to daily work
```

### 2. Protect branches (GitHub Settings → Branches)

| Branch | Protection |
|--------|------------|
| `main` | Require PR, require CI pass |
| `staging` | Require PR from `dev` |
| `cloud` | Require CI pass; allow merge from `staging` |
| `dev` | Default branch for PRs |

---

## Deploy `cloud` → Linode (15 minutes)

### Prerequisites

- Linode personal access token ([cloud.linode.com](https://cloud.linode.com))
- A VM with Ubuntu 22.04 (2GB is enough for preview)
- Ports **8080** (API) and **22** (SSH) open

### Path A — From your laptop (recommended for demos)

**Prerequisite:** validate locally with Docker + Postgres first:

```bash
cp .env.cloud.example .env.cloud
./deploy/scripts/cloud-docker-up.sh -d
./deploy/scripts/cloud-docker-smoke.sh
```

Then deploy to Linode:

```bash
# 1. Export your Linode root IP
export OMEM_LINODE_IP=203.0.113.10

# 2. Optional: protect the demo API
export OMEM_API_KEY="omem_sk_demo_$(openssl rand -hex 8)"

# 3. First boot only — install Docker + firewall
ssh root@$OMEM_LINODE_IP 'bash -s' < deploy/scripts/linode-setup.sh

# 4. Deploy the cloud branch
./deploy/scripts/cloud-proof-deploy.sh \
  --host "$OMEM_LINODE_IP" \
  --branch cloud \
  --api-key "$OMEM_API_KEY"
```

You get a live URL:

```text
http://<LINODE_IP>:8080/v1/health
http://<LINODE_IP>:8080/docs          ← Swagger for Akamai audience
http://<LINODE_IP>:8080/mcp/sse       ← MCP for Cursor / Claude
```

### Path B — SSH only (manual)

```bash
ssh root@<LINODE_IP> \
  OMEM_BRANCH=cloud OMEM_API_KEY=your_key \
  'bash -s' < deploy/scripts/linode-deploy-app.sh
```

---

## Akamai demo script (5 minutes live)

Run these from your laptop while sharing screen:

```bash
ENDPOINT="http://$OMEM_LINODE_IP:8080"
HDR=(-H "Content-Type: application/json")
[[ -n "$OMEM_API_KEY" ]] && HDR+=(-H "Authorization: Bearer $OMEM_API_KEY")

# 1. Health — service is up on Akamai Cloud
curl -s "$ENDPOINT/v1/health" | python3 -m json.tool

# 2. Remember — agent memory persists on managed infra
curl -s -X POST "$ENDPOINT/v1/remember" "${HDR[@]}" \
  -d '{"content":"Akamai edge caches static assets; OMem caches agent state","session_id":"akamai-demo","importance":0.95}'

# 3. Recall — hybrid retrieval (not just vector DB)
curl -s -X POST "$ENDPOINT/v1/recall" "${HDR[@]}" \
  -d '{"query":"agent state Akamai","session_id":"akamai-demo","k":3}'

# 4. Checkpoint — agent crash recovery (your differentiator)
curl -s -X POST "$ENDPOINT/v1/state/akamai-demo/checkpoint" "${HDR[@]}"

# 5. Context — token-efficient LLM input
curl -s -X POST "$ENDPOINT/v1/context/build" "${HDR[@]}" \
  -d '{"task":"explain OMem as Akamai service","session_id":"akamai-demo","budget_tokens":4000}'
```

**Talk track:** *"Same `pip install omem` SDK locally — point `OMEM_ENDPOINT` here and agents get managed state on Akamai infrastructure. No customer Postgres, no vector DB ops."*

---

## Connect SDK to your Linode demo

```bash
pip install omem
export OMEM_ENDPOINT="http://$OMEM_LINODE_IP:8080"
export OMEM_API_KEY="your_key"   # if set during deploy

python3 - <<'EOF'
from omem import AgentState
with AgentState(session_id="akamai-demo") as agent:
    agent.remember("Wizard competition: prove agent state as Akamai service")
    print(agent.recall("Akamai service"))
EOF
```

*(Cloud client auto-detect ships in v3.2; until then use REST or local AgentState against the endpoint via HTTP.)*

---

## Promotion workflow before a presentation

```bash
# 1. Ensure staging is green
git checkout staging && git pull
pytest tests/ -q

# 2. Promote to cloud
git checkout cloud
git merge staging -m "Promote staging to cloud demo"
git push origin cloud

# 3. Deploy
./deploy/scripts/cloud-proof-deploy.sh --host "$OMEM_LINODE_IP" --branch cloud

# 4. Tag the demo snapshot (optional)
git tag -a cloud-preview-$(date +%Y-%m-%d) -m "Akamai wizard demo"
git push origin --tags
```

---

## What to show Akamai leadership

| Proof point | Evidence |
|-------------|----------|
| Runs on Akamai Cloud (Linode) | Live IP + `/v1/health` |
| Agent memory + state, not just vectors | `/v1/remember`, `/v1/state/*/checkpoint` |
| MCP-native for coding agents | `/mcp/sse` + Cursor config |
| Enterprise path | Governance layer in OSS; auth middleware in v3.1 |
| OSS → managed service | Same repo, `cloud` branch deploys; PyPI for developers |

---

## Cost & teardown

- **Preview VM:** ~$12/mo (Linode 2GB shared)
- **Teardown after demo:** `./deploy/scripts/teardown.sh` or delete VM in Linode console

---

## Related

- [DEPLOY_GUIDE.md](../../deploy/DEPLOY_GUIDE.md) — full deployment paths
- [AKAMAI_LINODE_DEPLOYMENT.md](../roadmap/AKAMAI_LINODE_DEPLOYMENT.md) — production topology
- [ARCHITECTURE.md](../architecture/ARCHITECTURE.md) — six-layer product model
