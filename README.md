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

**Zero required LLM calls or API fees. Local-first hybrid recall. Postgres multi-tenancy. Built-in MCP for Cursor & Claude.**

[Quickstart](#quickstart) · [Why OMem](#why-omem-not-a-vector-db) · [Benchmarks](#benchmarks) · [MCP for Coding Agents](#mcp-for-coding-agents) · [Enterprise](#enterprise-postgresql) · [Architecture](#architecture)

</div>

---

## Layer maturity

| Layer | Status |
|-------|--------|
| Memory | Stable |
| State | Stable |
| Context | Stable |
| Knowledge | Partial — link/query API works; graph projection is in-memory, durable edges incomplete |
| Observe | Partial — Prometheus metrics work; Grafana dashboards are basic |
| Governance | Stable (local SQLite audit) / Preview (cloud RBAC + namespace headers) |

For managed, multi-tenant hosting see [OMem Cloud](../omem-cloud/).

### Known limitations

Default embeddings are hash-based (384-dim, zero extra dependencies). Recall quality is lower than `sentence-transformers` or OpenAI embeddings. For production semantic quality, install the optional `[embeddings]` extra: `pip install omem-os[embeddings]`.

---

## Benchmarks

Tested on Apple M-series · 5,000 memories · 500 queries · `all-MiniLM-L6-v2` · reproduce with `python distribution/benchmark_vs_mem0.py`

**Methodology:** OMem uses a fully local heuristic classification and
embedding/scoring path. The default script compares that measured local path
with a modeled Mem0 baseline representing an LLM-based extraction/scoring
configuration; use `--live-mem0` for a live Mem0 run. These are different
operation pipelines, so the latency ratios describe the tested configurations,
not equivalent underlying operations.

| System | Cold Start | Add | RAG p50 | RAG p99 | Est. third-party API fees / 1M recalls |
|---|---:|---:|---:|---:|---:|
| **OMem** | **4 ms** | **65 ops/s** | **1.8 ms** | **3.9 ms** | **$0** |
| Mem0 | 15,000 ms | <1 ops/s | 420 ms | 638 ms | ~$20 |
| ChromaDB | 507 ms | 277 ops/s | — | 4 ms | $0 |
| LanceDB | 8 ms | 82,000 ops/s | — | 7 ms | $0 |

**In this configuration, OMem measured 3.9 ms p99 local recall versus the
modeled Mem0 baseline of 638 ms (a 163× latency ratio), with $0 third-party API
fees. Local infrastructure costs are not included.**

OMem's `add()` does more than raw storage: embed, classify, deduplicate, sync
the knowledge graph, and persist asynchronously. The benchmark reflects each
system's configured workflow, not a raw vector-insert comparison.

---

## Why OMem, Not a Vector DB

Most agent frameworks bolt on a vector store and call it "memory." OMem is a **complete memory operating system** — it answers the questions production agents actually ask:

> *Why did we make this architectural decision? What did PR #142 change? Have we seen this bug before? Can I roll back? Can I audit?*

| What agents need | Vector DB | Mem0 | **OMem** |
|---|:---:|:---:|:---:|
| Semantic recall | ✓ | ✓ | ✓ |
| Keyword + recency + graph fusion | ✗ | ✗ | ✓ |
| Persistent cross-session memory | ✗ | ✓ | ✓ |
| No required third-party API fees (local path) | ✓ | ✗ | ✓ |
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

Full `AgentState` API (four product layers + cross-cutting gov/observe):

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
brain.add("[ADR] Use Rust for local scoring to avoid third-party ranking calls.")

# Session 2 — completely new process, no shared state
brain2 = OMem(namespace="my-project")
results = brain2.recall("why do we use Rust")
# → Returns the ADR from Session 1 without a required LLM or API call.
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

## OMem Cloud

**OMem Cloud** is a commercial product that wraps the open-source core with a production-grade managed service: multi-tenant API, PostgreSQL + pgvector backend, background worker, Prometheus/Grafana observability, NGINX, and one-command Linode/Akamai deployment via Terraform.

| Feature | omem-os (open source) | omem-cloud (commercial) |
|---|---|---|
| Local SQLite memory | ✅ | ✅ |
| MCP server | ✅ | ✅ |
| All integrations | ✅ | ✅ |
| Multi-tenant REST API | — | ✅ |
| PostgreSQL + pgvector | ✅ backend only | ✅ managed stack |
| Production Docker deploy | — | ✅ |
| Linode / Akamai Terraform | — | ✅ |
| Prometheus + Grafana | — | ✅ |
| SLA support | — | ✅ |

> **Get access:** [https://omem.dev/cloud](https://omem.dev/cloud) · [support@omem.dev](mailto:support@omem.dev)

### Enterprise PostgreSQL Backend (open source)

The PostgreSQL backend itself is open source and ships with `omem-os`. You can use it with your own Postgres instance without omem-cloud:

```python
from omem.backends.postgres_enterprise import EnterprisePostgresBackend

backend = EnterprisePostgresBackend(
    connection_string="postgresql://omem:secret@localhost:5432/omem",
    org_id="acme-corp",
    user_id="alice",
)
# All reads/writes are structurally isolated to (acme-corp, alice)
```

---

## Architecture

OMem exposes **four product layers** (Memory, State, Context, Knowledge).
**Governance & Observability are cross-cutting** — they apply to every operation
in every layer above, not sequential layers stacked after Knowledge.

```
┌─────────────────────────────────────────────────────────────┐
│                      Agent / MCP Client                      │
├──────────────┬──────────────┬──────────────┬─────────────────┤
│   Memory      │    State     │   Context    │   Knowledge     │
│  add/recall/  │  snapshot/   │  token-      │  entity graph   │
│  reflect/sleep│  fork/rollback│ budget     │  + AST index*   │
├──────────────┴──────────────┴──────────────┴─────────────────┤
│  Governance & Observability  (cross-cutting — every op)       │
│  audit · RBAC · retention · encryption · traces · metrics     │
│  · OTel (partial: /v1/remember path in omem-cloud)            │
├─────────────────────────────────────────────────────────────┤
│  Engine:  BrainTrace** (Python) + omem_rust (Rayon/PyO3)      │
├─────────────────────────────────────────────────────────────┤
│  Backend: SQLite (local) │ PostgreSQL + pgvector (enterprise) │
└─────────────────────────────────────────────────────────────┘
```

\* **FLAG — confirm before customer-facing use:** Knowledge currently lists
  “AST codebase index”. Keep, drop, or reword? (see Phase 4 review)

\*\* **FLAG — confirm before customer-facing use:** Engine internal name is
  `BrainTrace`. Keep that name publicly, or say “core engine” only?

### Scoring Formula

```
score = α·semantic + β·keyword + γ·recency + δ·importance + ε·confidence + ζ·graph
```

Weights adapt per retrieval mode: `coding`, `planning`, `chat`, `recall`. In
the Apple M-series benchmark above, the Rust hot path (`rag_score_batch`)
evaluates candidates in parallel using Rayon work-stealing; end-to-end local
recall measured 3.9 ms p99 at N=5,000. Results vary by hardware, dataset, and
embedding configuration.

### File Map

| Path | Purpose |
|---|---|
| `omem/integrations/mcp_server.py` | MCP server — coding agent tools |
| `rust/src/lib.rs` | Rust scoring engine (PyO3 + Rayon) |
| `omem/backends/postgres_enterprise.py` | Enterprise multi-tenant backend |
| `omem/agent_state.py` | `AgentState` facade (4 product layers + cross-cutting gov/observe) |
| `omem/core/engine/` | BrainTrace orchestrator |
| `omem/core/brain/` | Importance, forgetting, dreaming, TMS |
| `omem/core/retrieval/` | Fusion, BM25, vector, ranker |
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
pip install "omem-os[all]"              # everything open-source
# omem-cloud (managed API server) → https://omem.dev/cloud
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
| Codebase AST indexing | Alpha |
| Managed cloud API (omem-cloud) | [Commercial](https://omem.dev/cloud) |
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

**[Engineering Blog](./distribution/engineering_blog.md) · [Benchmark](./distribution/benchmark_vs_mem0.py) · [MCP Setup](./docs/guides/MCP_SETUP.md) · [OMem Cloud](https://omem.dev/cloud)**

</div>
