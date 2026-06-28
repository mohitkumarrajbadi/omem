<div align="center">

[![PyPI](https://img.shields.io/pypi/v/omem-os?style=for-the-badge&color=brightgreen)](https://pypi.org/project/omem-os/)
[![CI](https://img.shields.io/github/actions/workflow/status/mohitkumarrajbadi/omem/ci.yml?branch=main&style=for-the-badge)](https://github.com/mohitkumarrajbadi/omem/actions)
[![Python](https://img.shields.io/badge/python-3.9%2B-blue?style=for-the-badge&logo=python)](https://www.python.org/)
[![Rust](https://img.shields.io/badge/rust-powered-orange?style=for-the-badge&logo=rust)](./rust/src/lib.rs)
[![License](https://img.shields.io/badge/license-MIT-green?style=for-the-badge)](./LICENSE)
[![MCP](https://img.shields.io/badge/MCP-Cursor%20%2F%20Claude-purple?style=for-the-badge)](./docs/guides/MCP_SETUP.md)
[![STATE-Bench](https://img.shields.io/badge/STATE--Bench-81.2%2F100-brightgreen?style=for-the-badge)](./benchmarks/state_bench.py)

<br>

# OMem

### The Memory OS for Enterprise AI Agents

**Sub-4ms hybrid recall. Zero API costs. Postgres multi-tenancy. Built-in MCP for Cursor & Claude.**

[Quickstart](#quickstart) · [Why OMem](#why-omem-not-a-vector-db) · [Benchmarks](#benchmarks) · [MCP for Coding Agents](#mcp-for-coding-agents) · [Enterprise](#enterprise-postgresql) · [Architecture](#architecture)

</div>

---

## Benchmarks

Tested on Apple M-series · 5,000 memories · 500 queries · `all-MiniLM-L6-v2` · reproduce with `python distribution/benchmark_vs_mem0.py`

| System | Cold Start | Add | RAG p50 | RAG p99 | Cost / 1M recalls |
|---|---:|---:|---:|---:|---:|
| **OMem** | **4 ms** | **65 ops/s** | **1.8 ms** | **3.9 ms** | **$0** |
| Mem0 | 15,000 ms | <1 ops/s | 420 ms | 638 ms | ~$20 |
| ChromaDB | 507 ms | 277 ops/s | — | 4 ms | $0 |
| LanceDB | 8 ms | 82,000 ops/s | — | 7 ms | $0 |

**163× faster p99 recall than Mem0. $0 API cost. No data leaves your infrastructure.**

OMem's `add()` does more than raw storage: embed, classify, deduplicate, sync the knowledge graph, and persist asynchronously. The benchmark reflects real agent memory behavior, not raw vector insert speed.

---

## Why OMem, Not a Vector DB

Most agent frameworks bolt on a vector store and call it "memory." OMem is a **complete memory operating system** — it answers the questions production agents actually ask:

> *Why did we make this architectural decision? What did PR #142 change? Have we seen this bug before? Can I roll back? Can I audit?*

| What agents need | Vector DB | Mem0 | **OMem** |
|---|:---:|:---:|:---:|
| Semantic recall | ✓ | ✓ | ✓ |
| Keyword + recency + graph fusion | ✗ | ✗ | ✓ |
| Persistent cross-session memory | ✗ | ✓ | ✓ |
| $0 API cost (local embeddings + scoring) | ✓ | ✗ | ✓ |
| Memory lifecycle (forget, compress, dream) | ✗ | ✗ | ✓ |
| Architectural decision records (ADRs) | ✗ | ✗ | ✓ |
| PR context & bug fix history | ✗ | ✗ | ✓ |
| State fork / rollback (git-like) | ✗ | ✗ | ✓ |
| Enterprise multi-tenant isolation | ✗ | ✗ | ✓ |
| MCP for Cursor / Claude | ✗ | ✗ | ✓ |

---

## Quickstart

```bash
pip install omem-os
```

```python
from omem import OMem

brain = OMem()  # persists to ~/.omem/brain.db — zero config

brain.add("Decision: use PostgreSQL with pgvector for the cloud deployment.")
brain.add("Bug fix: WriteBuffer race condition. Fix: RWLock on KVCache mutations.", importance=0.95)
brain.add("PR #142 merged: multi-tenant org_id/user_id columns added.")

for mem in brain.recall("database choice", k=3):
    print(f"[{mem.importance:.2f}] {mem.content}")
```

Full `AgentState` API (six-layer stack):

```python
from omem import AgentState

with AgentState(session_id="my-agent") as agent:
    # Memory
    agent.remember("FastAPI uses Pydantic v2 for validation", importance=0.9)

    # State — git-like snapshots
    agent.set_goal("Ship auth middleware by Friday")
    snap = agent.snapshot(label="before-auth-refactor")

    # Knowledge graph
    agent.learn("FastAPI", "uses", "Pydantic")

    # Token-efficient context assembly
    ctx = agent.build_context("implement auth middleware", budget_tokens=4000)
    # ctx.text → ready to inject into your LLM prompt

    # Explainability — why was this recalled?
    print(agent.explain("framework choice").format())

    # Fork — evaluate two approaches in parallel
    plan_a = agent.clone("plan-fastapi")
    plan_b = agent.clone("plan-django")
```

---

## MCP for Coding Agents

OMem is the best memory layer for [Cursor](https://cursor.sh) and [Claude Code](https://claude.ai/code). It gives your agent the institutional knowledge of a senior engineer who has been on the project for months — **across every session**.

### Install

```bash
pip install "omem-os[mcp]"
omem serve
```

### Add to `claude_desktop_config.json` / Cursor MCP settings

```json
{
  "mcpServers": {
    "omem": {
      "command": "omem",
      "args": ["serve"]
    }
  }
}
```

### What the Agent Remembers

| MCP Tool | What it stores |
|---|---|
| `remember_decision` | Architectural decision records (ADRs): why PostgreSQL, why GraphQL, tradeoffs |
| `recall_decisions` | Surface past ADRs before making a technical choice |
| `remember_pr_context` | PR title, description, files changed, review notes, merge decision |
| `recall_pr_context` | Answer "why was this changed?" without reading git log |
| `remember_bug_fix` | Root cause + fix for recurring issues |
| `recall_bugs` | Surface prior fixes before re-investigating the same error |
| `query_codebase` | Semantic AST search — replaces grep for code navigation |
| `ingest_codebase` | One-time full AST index of the repository |
| `sync_codebase` | Incremental post-commit update via git diff |
| `get_codebase_summary` | Birds-eye view: ADRs + recent PRs + memory stats |

### Demo: Context Survives Process Boundaries

```python
# Session 1 — architect agent stores decisions
brain = OMem(namespace="my-project")
brain.add("[ADR] Use Rust for scoring: bypass Python GIL, achieve sub-4ms p99.")

# Session 2 — completely new process, no shared state
brain2 = OMem(namespace="my-project")
results = brain2.recall("why do we use Rust")
# → Returns the ADR from Session 1 in <4ms. No LLM call. No API cost.
```

Run the full demo: `python demo_mcp_coding_workflow.py`

### MCP Resources (read-only snapshots)

| Resource URI | Contents |
|---|---|
| `omem://decisions` | All stored architectural decision records |
| `omem://pr_history` | Pull request context (title, files, review notes) |
| `omem://bug_fixes` | Known bug fixes with root cause analysis |
| `omem://recent` | 20 most recent memories |
| `omem://status` | Memory distribution and health stats |

---

## Enterprise PostgreSQL

Production-grade multi-tenant deployment for enterprise AI agent fleets.

### Architecture

```
                     ┌─────────────────────────────────────────┐
                     │           Enterprise Stack               │
         Agents ───▶ │  nginx (TLS) ──▶ OMem API (×N)          │
                     │                      │                   │
                     │  PgBouncer (pool) ───▶ PostgreSQL 16      │
                     │  + pgvector (ANN)    + Row-Level Security │
                     │  + RLS policies      + Tenant isolation   │
                     │                                          │
                     │  Worker (maintain)   Prometheus + Grafana │
                     └─────────────────────────────────────────┘
```

### Multi-Tenant Isolation

Every memory is scoped to `(org_id, user_id)`. Tenant isolation operates at **three independent layers**:

1. **Application layer**: all queries include `WHERE org_id = ? AND user_id = ?`
2. **Database RLS**: Postgres row-level security policies block cross-tenant access even if application code has a bug
3. **Session context**: `SET LOCAL omem.org_id = 'acme'` enforces isolation at the connection level

```sql
-- Row-level security policy (from init-enterprise.sql)
CREATE POLICY memories_tenant_rls ON memories
    USING (
        org_id  = current_setting('omem.org_id',  true)
        AND
        user_id = current_setting('omem.user_id', true)
    );
```

### Quick Deploy

```bash
# 1. Configure secrets
cp .env.cloud.example .env.enterprise
# Edit: POSTGRES_PASSWORD, OMEM_API_KEY, OMEM_SECRET_KEY

# 2. Start the enterprise stack (pgvector + PgBouncer + OMem + monitoring)
docker compose -f deploy/docker/docker-compose.enterprise.yml up -d

# 3. Add monitoring
docker compose -f deploy/docker/docker-compose.enterprise.yml --profile monitoring up -d

# 4. Verify
curl http://localhost/v1/health
# {"status": "healthy", "backend": "postgres", ...}
```

### Enterprise Stack Services

| Service | Image | Role |
|---|---|---|
| `omem-db` | `pgvector/pgvector:pg16` | Primary DB with native vector ANN |
| `pgbouncer` | `edoburu/pgbouncer` | Connection pooler (2,000 clients → 50 DB connections) |
| `omem-api` | `omem-cloud:latest` | FastAPI REST + MCP/SSE |
| `omem-worker` | `omem-cloud:latest` | Background memory maintenance |
| `nginx` | `nginx:alpine` | TLS termination + load balancing |
| `prometheus` | `prom/prometheus` | Metrics scraping |
| `grafana` | `grafana/grafana` | Dashboards |

### Enterprise Backend

```python
from omem.backends.postgres_enterprise import EnterprisePostgresBackend

backend = EnterprisePostgresBackend(
    connection_string="postgresql://omem:secret@pgbouncer:5432/omem",
    org_id="acme-corp",
    user_id="alice",
)
# All reads/writes are structurally isolated to (acme-corp, alice)
```

---

## Architecture

OMem is a six-layer agent state platform. Each layer is independently useful; together they form a complete agent infrastructure stack.

```
┌────────────────────────────────────────────────────────────┐
│                     Agent / MCP Client                      │
├────────────────────────────────────────────────────────────┤
│  Layer 1: Memory OS    add, recall, reflect, sleep, inspect │
│  Layer 2: State OS     snapshot, fork, rollback, resume     │
│  Layer 3: Context      token-budget prompt assembly         │
│  Layer 4: Knowledge    entity graph + AST codebase index    │
│  Layer 5: Observe      traces, metrics, OpenTelemetry       │
│  Layer 6: Governance   audit, RBAC, retention, encryption   │
├────────────────────────────────────────────────────────────┤
│  Engine:  BrainTrace (Python) + omem_rust (Rayon/PyO3)     │
├────────────────────────────────────────────────────────────┤
│  Backend: SQLite (local) │ PostgreSQL + pgvector (enterprise)│
└────────────────────────────────────────────────────────────┘
```

### Scoring Formula

```
score = α·semantic + β·keyword + γ·recency + δ·importance + ε·confidence + ζ·graph
```

Weights adapt per retrieval mode: `coding`, `planning`, `chat`, `recall`. The Rust hot path (`rag_score_batch`) evaluates this in parallel across all candidates using Rayon work-stealing, achieving sub-4ms p99 at N=5,000.

### File Map

| Path | Purpose |
|---|---|
| `omem/integrations/mcp_server.py` | MCP server — coding agent tools |
| `rust/src/lib.rs` | Rust scoring engine (PyO3 + Rayon) |
| `omem/backends/postgres_enterprise.py` | Enterprise multi-tenant backend |
| `omem/agent_state.py` | Six-layer `AgentState` facade |
| `omem/core/engine/` | BrainTrace orchestrator |
| `omem/core/brain/` | Importance, forgetting, dreaming, TMS |
| `omem/core/retrieval/` | Fusion, BM25, vector, ranker |
| `deploy/docker/docker-compose.enterprise.yml` | Enterprise stack |
| `deploy/docker/init-enterprise.sql` | pgvector schema + RLS |
| `distribution/benchmark_vs_mem0.py` | Reproducible benchmark |
| `distribution/engineering_blog.md` | Technical deep-dive |
| `demo_mcp_coding_workflow.py` | Cross-session context demo |

---

## State Forking

Evaluate multiple realities in parallel — no other memory system has this:

```python
agent = AgentState(session_id="planner")
agent.snapshot(label="decision-point")

plan_a = agent.clone("plan-postgres")
plan_b = agent.clone("plan-dynamodb")

# Each fork is completely independent — different memories, different state
plan_a.remember("PostgreSQL: mature, RLS, pgvector support")
plan_b.remember("DynamoDB: serverless, but no vector search")

# Run evaluations, then merge the winner back
```

---

## Explainability

Full score decomposition for every recall decision:

```
╔══ Explain: 'What database should I use?'
║  session=planner  mode=coding  elapsed=2.1ms
╠══════════════════════════════════════════════════
║  [1] score=0.8821  id=a3f9...
║      vector=0.721  keyword=0.850  recency=1.000
║      importance=0.900  graph=0.760
║      type=SEMANTIC  → [ADR] Use PostgreSQL for production
╚══════════════════════════════════════════════════
```

---

## STATE-Bench

The only benchmark that measures what agent state systems actually need:

```bash
omem bench              # run all suites (~2 seconds)
omem bench --json       # CI-friendly output
```

| Suite | Score | What it measures |
|---|---|---|
| **State** | 100/100 | Snapshot, rollback, fork, checkpoint recovery |
| **Explainability** | 100/100 | Score decomposition, provenance, latency |
| **Concurrency** | 100/100 | Parallel agent throughput (3,000+ ops/s) |
| **Context** | 67/100 | Token savings, budget adherence |
| **Continuity** | 67/100 | Crash recovery, workflow resume |
| **Memory** | 54/100 | Recall@K, MRR, latency |
| **Overall** | **81/100** | `STATE-Bench v1.0` |

---

## CLI

```bash
omem serve                                      # start MCP server for Cursor/Claude
omem add "Decision: use GraphQL for the API" -i 0.9
omem search "database decision" -k 5
omem inspect "database decision"                # score decomposition
omem maintain --all                             # compress + forget + consolidate
omem bench --suite state --suite memory         # run benchmarks
omem ingest .                                   # index codebase AST
omem sync .                                     # incremental update (git diff)
omem codebase "auth token refresh logic"        # semantic code search
```

---

## Install Options

```bash
pip install omem-os                     # core (SQLite, hash embeddings)
pip install "omem-os[mcp]"              # + MCP server for Cursor/Claude
pip install "omem-os[fast]"             # + FAISS + sentence-transformers
pip install "omem-os[postgres]"         # + PostgreSQL backend
pip install "omem-os[cloud]"            # + FastAPI cloud server
pip install "omem-os[all]"              # everything
```

From source with Rust acceleration:

```bash
git clone https://github.com/mohitkumarrajbadi/omem
cd omem
pip install -e ".[all]"                 # Rust compiled automatically via maturin
pytest tests/ -v
```

---

## Stability

| Component | Status |
|---|---|
| Core API: `add`, `recall`, `sleep`, `inspect` | Stable |
| SQLite backend | Stable |
| MCP server (Cursor / Claude) | Stable |
| Coding agent tools (ADRs, PRs, bugs) | Stable |
| PostgreSQL backend | Beta |
| Enterprise multi-tenant backend | Beta |
| Enterprise docker-compose + pgvector | Beta |
| Codebase AST indexing | Alpha |
| LangChain integration | Beta |
| CrewAI integration | Alpha |

---

## FAQ

**Does OMem call an LLM internally?**
No. Importance scoring, entity extraction, and memory ranking all use local heuristics and Rust-accelerated algorithms. No API keys required.

**How is this different from a vector database?**
Vector databases store vectors. OMem manages the full memory lifecycle: importance scoring, conflict resolution, forgetting, consolidation, state snapshots, knowledge graph, governance, and MCP integration. It is an operating system for memory, not a storage layer.

**What is the Rust layer actually doing?**
`rag_score_batch` parallelizes hybrid scoring (vector + BM25 + recency + importance + type boost) across all candidate memories using Rayon's work-stealing thread pool. At N=5,000, this runs in ~1ms on Apple M-series.

**How does multi-tenant isolation work?**
Three independent layers: (1) application-level `org_id`/`user_id` WHERE clauses, (2) PostgreSQL row-level security policies that block cross-tenant reads at the DB layer, (3) per-connection `SET LOCAL omem.org_id` session variables.

**Is my data sent anywhere?**
No. OMem is local-first. The default SQLite backend stores everything on disk at `~/.omem/brain.db`. The enterprise Postgres backend runs in your own infrastructure. No telemetry, no cloud dependency.

---

## License

MIT — see [LICENSE](./LICENSE).

---

<div align="center">

**[Engineering Blog](./distribution/engineering_blog.md) · [Benchmark](./distribution/benchmark_vs_mem0.py) · [MCP Setup](./docs/guides/MCP_SETUP.md) · [Enterprise Deploy](./deploy/DEPLOY_GUIDE.md)**

</div>
