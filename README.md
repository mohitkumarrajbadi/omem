<div align="center">

[![PyPI](https://img.shields.io/pypi/v/omem-os?style=for-the-badge&color=brightgreen)](https://pypi.org/project/omem-os/)
[![CI](https://img.shields.io/github/actions/workflow/status/mohitkumarrajbadi/omem/ci.yml?branch=main&style=for-the-badge)](https://github.com/mohitkumarrajbadi/omem/actions)
[![Python](https://img.shields.io/badge/python-3.9%2B-blue?style=for-the-badge&logo=python)](https://www.python.org/)
[![Rust](https://img.shields.io/badge/rust-powered-orange?style=for-the-badge&logo=rust)](./rust/src/lib.rs)
[![License](https://img.shields.io/badge/license-MIT-green?style=for-the-badge)](./LICENSE)
[![MCP](https://img.shields.io/badge/MCP-Cursor%20%2F%20Claude-purple?style=for-the-badge)](./docs/guides/MCP_SETUP.md)
[![STATE-Bench](https://img.shields.io/badge/STATE--Bench-80.6%2F100-brightgreen?style=for-the-badge)](./benchmarks/state_bench.py)

<br>

# OMem

### Governed Agent Memory

**Every memory system can tell your agent what it remembers.
OMem can prove it — what it knew, when it knew it, and who is allowed to see it.**

Local-first hybrid recall · audit / retention / tenant hardening as architecture ·
optional Postgres multi-tenancy · MCP for Cursor & Claude · design-partner tech preview for cloud.

**Current development line: 0.0.3 (unreleased).** Latest public artifacts:
0.0.1 on PyPI and v0.0.2 on GitHub.

[Quickstart](#quickstart) · [Why governed memory](#why-governed-agent-memory) · [Design partners](./docs/design-partner/README.md) · [Benchmarks](#benchmarks) · [Architecture](#architecture)

</div>

---

## Why Governed Agent Memory

Agent memory is a crowded category. Storing embeddings is table stakes.
What enterprises still cannot answer in an audit or security review:

> *Prove what the agent knew at time T. Show who approved that fact.
> Show that Org A cannot read Org B. Show that PAN never sat plaintext on disk.*

OMem treats **Provenance + Governance + Runtime** as first-class layers beside
Memory / State / Knowledge — not bolt-ons. That is the wedge.

| Question | Typical memory layer | **OMem** |
|---|---|---|
| What did we recall? | ✓ | ✓ |
| When was it valid / superseded? | Weak | Provenance + belief revision |
| Who is allowed to see it? | Bolt-on / missing | `harden_namespace`, tenant scopes |
| Can SecOps export the trail? | Rarely | `governance.export_audit` / CLI JSON |
| Encryption at rest | Often “roadmap” | AES-256-GCM when key present |
| Roll back agent state? | Rarely | Git-like state fork / rollback |

Marketing one-liners (pick one):

- *Mem0 remembers. Zep remembers when. OMem remembers — and can show the auditor who approved it.*
- *Built for the market’s next question: not “does it recall,” but “can you defend it in an audit.”*
- *The compliance team’s favorite AI memory layer.*

**Not competing as “another Mem0.”** Competing as the governance-and-audit layer
every memory system is missing — closer to Atlan-for-agents than to a vector DB.

Design-partner pack: [docs/design-partner/](./docs/design-partner/README.md) ·
Guarantees: [docs/guarantees/TENANT_HARDENING.md](./docs/guarantees/TENANT_HARDENING.md)

---

## Layer maturity

| Layer | Status |
|-------|--------|
| Memory | Stable — local API and lifecycle covered by the OSS test suite |
| State | Stable — snapshots, rollback, forks, and checkpoints covered |
| Context | Stable — token budgeting and context assembly covered |
| Knowledge | Beta — link/query/reasoning covered; Python-only AST index remains Alpha |
| Observe | Beta — local traces **Stable**; OTLP JSON export/push covers **in-process** ObserveOS events only (not full auto-instrumentation); HTTP-path OTel is **omem-cloud only** (partial `/v1/remember`); dashboard remains Alpha |
| Governance | Stable for local audit/retention/encryption; tenant and cloud enforcement remain Beta |

For managed, multi-tenant hosting see [OMem Cloud](../omem-cloud/)
(**design-partner tech preview** — not GA).

### Known limitations

**The default 384-dimensional hash embeddings prioritize zero-configuration
installation, not semantic quality. Recall quality is weaker than with
`sentence-transformers` or OpenAI embeddings.** For production semantic
retrieval, install the optional model-backed extra:
`pip install "omem-os[embeddings]"`.

**OTel / OTLP:** HTTP-path OpenTelemetry instrumentation is currently available
only in omem-cloud, and only partially (`/v1/remember`). omem-os can
export/push OTLP JSON for **in-process** ObserveOS traces; it does **not**
claim full OpenTelemetry auto-instrumentation of the runtime. Broader OTel
coverage is on the near-term roadmap.

---

## Benchmarks

These numbers are measured against our own system end-to-end. For a modeled
comparison against other frameworks and its methodology caveats, see
[distribution/benchmark_methodology.md](./distribution/benchmark_methodology.md).

Honest retrieval / state scores — **no LLM judge**. Full report:
[`distribution/public_benchmark_results.json`](./distribution/public_benchmark_results.json).

```bash
pip install "omem-os[embeddings]"
python -m benchmarks.public_memory_suite --subset 40 --k 5
omem bench --json    # STATE-Bench only
```

| Benchmark | Metric | Score | Caveat |
|---|---|---:|---|
| **STATE-Bench** | Overall | **80.6/100** | Native agent-state suites |
| **LongMemEval** (oracle, n=40) | Answer in top-5 | **72.5%** | Retrieval-only, not E2E QA |
| **LoCoMo** (80 QA) | Answer **or** evidence in top-5 | **66.2%** | Not generative QA |
| **BEAM-style** (10 abilities) | Ability pass rate | **100%** | Synthetic suite, **not** official BEAM |

These numbers are for diligence checkboxes (“we tested this”), not leaderboard claims.

### STATE-Bench breakdown

| Suite | Score | What it measures |
|---|---|---|
| **Memory** | 100/100 | Recall@K, MRR, latency |
| **State** | 100/100 | Snapshot, rollback, fork, checkpoint recovery |
| **Explainability** | 100/100 | Score decomposition, provenance, latency |
| **Context** | 67/100 | Token savings, budget adherence |
| **Continuity** | 67/100 | Crash recovery, workflow resume |
| **Concurrency** | 50/100 | Parallel agent throughput |
| **Overall** | **80.6/100** | `STATE-Bench v1.0` · `all-MiniLM-L6-v2` |

Reproduce with `python benchmarks/state_bench.py --json`.

---

## Why OMem still beats a vector DB

Governance is the wedge; recall is still table stakes. OMem is a **memory OS**
for production agents — not a vector store with marketing:

> *Why did we make this architectural decision? What did PR #142 change?
> Have we seen this bug before? Can I roll back? Can I audit?*

| What agents need | Vector DB | Mem0 | **OMem** |
|---|:---:|:---:|:---:|
| Semantic recall | ✓ | ✓ | ✓ |
| Keyword + recency + graph fusion | ✗ | ✗ | ✓ |
| Persistent cross-session memory | ✗ | ✓ | ✓ |
| No required third-party API fees (local path) | ✓ | ✗ | ✓ |
| Memory lifecycle (forget, compress, dream) | ✗ | ✗ | ✓ |
| Audit export / retention / encryption | ✗ | Bolt-on | **First-class** |
| Architectural decision records (ADRs) | ✗ | ✗ | ✓ |
| State fork / rollback (git-like) | ✗ | ✗ | ✓ |
| Tenant hardening primitives | ✗ | ✗ | ✓ |
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

### Add to Claude Code / OpenCode / Cursor MCP settings

**Personal production (shared memory across tools):** see [`docs/guides/PERSONAL_MCP.md`](./docs/guides/PERSONAL_MCP.md)

```json
{
  "mcpServers": {
    "omem": {
      "command": "omem",
      "args": ["serve", "--namespace", "personal", "--db-path", "~/.omem/brain.db"]
    }
  }
}
```

Ready-made configs: `deploy/mcp/claude_code.mcp.json`, `opencode.mcp.json`, `cursor.mcp.json`.

Verify:

```bash
python3 scripts/mcp_personal_smoke.py
```

### Add to `claude_desktop_config.json` (legacy short form)

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
| `query_codebase` | Semantic AST search — Python-only AST index (Alpha); replaces grep for code navigation |
| `ingest_codebase` | One-time full Python-only AST index of the repository (Alpha) |
| `sync_codebase` | Incremental post-commit update via git diff (Python-only AST index, Alpha) |
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

**OMem Cloud** is a commercial product that wraps the open-source core with a production-grade managed service: multi-tenant API, PostgreSQL + pgvector backend, background worker, Prometheus/Grafana observability, NGINX, and one-command Linode/Akamai deployment via Terraform. **Status: design-partner tech preview — not GA.** OMem Cloud's SOC2 Type I evidence collection is **not yet started**, tracked in [docs/guarantees/TENANT_HARDENING.md](./docs/guarantees/TENANT_HARDENING.md).

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
│  reflect/sleep│  fork/rollback│ budget     │  + Python-only  │
│               │               │            │    AST index    │
│               │               │            │    (Alpha)      │
├──────────────┴──────────────┴──────────────┴─────────────────┤
│  Governance & Observability  (cross-cutting — every op)       │
│  audit · RBAC · retention · encryption · traces · metrics     │
│  · OTel export — omem-cloud only for HTTP-path instrumentation
│    (partial: /v1/remember); not automatic request tracing in omem-os
│  · OSS ObserveOS: optional OTLP JSON export/push for in-process traces
├─────────────────────────────────────────────────────────────┤
│  Engine:  core engine (Python) + omem_rust (Rayon/PyO3)       │
├─────────────────────────────────────────────────────────────┤
│  Backend: SQLite (local) │ PostgreSQL + pgvector (enterprise) │
└─────────────────────────────────────────────────────────────┘
```

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
| `omem/core/engine/` | Core engine orchestrator (internal module layout) |
| `omem/core/brain/` | Importance, forgetting, dreaming, TMS |
| `omem/core/retrieval/` | Fusion, BM25, vector, ranker |
| `distribution/benchmark_vs_mem0.py` | Modeled latency comparison (see methodology notes) |
| `distribution/benchmark_methodology.md` | Caveats for modeled competitor comparison |
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

These labels reflect the current OSS test boundary. The local Python suite
covers Memory, State, Context, Knowledge, Observe, Governance, SQLite, and
adapter behavior. It does **not** run a live PostgreSQL service, a real
Cursor/Claude MCP client, upstream LangChain/CrewAI agents, or browser-based
dashboard tests.

| Component | Status |
|---|---|
| Core API: `add`, `recall`, `sleep`, `inspect` | Stable — unit and end-to-end local coverage |
| SQLite backend | Stable — persistent and in-memory behavior covered |
| MCP server (Cursor / Claude) | Beta — imports and tool structures covered; no real-client CI |
| Coding agent tools (ADRs, PRs, bugs) | Beta — implemented; no end-to-end MCP client coverage |
| PostgreSQL backend | Beta — implementation present; no live-Postgres OSS CI |
| Enterprise multi-tenant backend | Beta — isolation design present; live RLS verification belongs to omem-cloud |
| Codebase AST indexing | Alpha — Python-only parser; import coverage, no repository-scale CI |
| Local dashboard | Alpha — server implemented; import coverage, no browser/end-to-end CI |
| Managed cloud API (omem-cloud) | [Commercial](https://omem.dev/cloud) |
| LangChain-style adapter | Beta — adapter contract covered; no upstream LangChain CI |
| CrewAI-style shared-memory adapter | Alpha — standalone adapter; no upstream CrewAI CI |

---

## FAQ

**Does OMem call an LLM internally?**
Not on the default path. Importance scoring, entity extraction, and memory
ranking use local heuristics and Rust-accelerated algorithms, so no API key is
required. Optional embedding providers can make external model/API calls when
explicitly configured.

**How is this different from a vector database?**
Vector databases store vectors. OMem manages the full memory lifecycle: importance scoring, conflict resolution, forgetting, consolidation, state snapshots, knowledge graph, governance, and MCP integration. It is an operating system for memory, not a storage layer.

**What is the Rust layer actually doing?**
`rag_fuse_batch` parallelizes multi-signal fusion across candidate memories
using Rayon's work-stealing thread pool; Rust also accelerates BM25 and graph
BFS when the compiled extension is available. Python fallbacks preserve
correctness without Rust. See the benchmark methodology above for the measured
hardware and workload.

**How does multi-tenant isolation work?**
The enterprise Postgres design uses three layers: (1) application-level
`org_id`/`user_id` filters, (2) PostgreSQL row-level security policies, and
(3) per-connection `SET LOCAL omem.org_id` session variables. The OSS unit
suite covers tenant scoping logic but does not run live PostgreSQL RLS tests;
those integration checks belong to `omem-cloud`.

**Is my data sent anywhere?**
No. OMem is local-first. The default SQLite backend stores everything on disk at `~/.omem/brain.db`. The enterprise Postgres backend runs in your own infrastructure. No telemetry, no cloud dependency.

---

## License

MIT — see [LICENSE](./LICENSE).

---

<div align="center">

**[Engineering Blog](./distribution/engineering_blog.md) · [Benchmark](./distribution/benchmark_vs_mem0.py) · [MCP Setup](./docs/guides/MCP_SETUP.md) · [Personal MCP (Claude Code + OpenCode)](./docs/guides/PERSONAL_MCP.md) · [OMem Cloud](https://omem.dev/cloud)**

</div>
