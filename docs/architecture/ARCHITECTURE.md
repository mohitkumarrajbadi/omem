# OMem Architecture

**Persistent State Infrastructure for AI Systems**

This document is the canonical reference for how OMem is organized. One import
(`AgentState`), **four product layers** plus **cross-cutting Governance &
Observability**, one engine boundary, zero ambiguity about where code belongs.

---

## Design Principles

| Principle | What it means |
|-----------|---------------|
| **One front door** | Developers import `AgentState` (or layer facades). Internal engine stays private. |
| **Layers, not lumps** | Every feature maps to exactly one layer. Extensions live *inside* that layer. |
| **Thin facades, fat core** | Public packages delegate to `core/` — never duplicate engine logic. |
| **Local-first** | Base install works offline with SQLite. Cloud is opt-in via env vars. |
| **Secure by default** | Audit, encryption, and RBAC live in Governance. Secrets never hit shared memory. |
| **Stable v1, evolving v2** | `OMem` stays forever-compatible. New work ships through layer facades. |

---

## System Overview

```text
                    Agent / MCP Client
                            │
        ┌───────────────────┼───────────────────┐
        ▼                   ▼                   ▼
   ┌─────────┐        ┌─────────┐        ┌──────────┐   ┌───────────┐
   │ Memory  │        │  State  │        │ Context  │   │ Knowledge │
   └────┬────┘        └────┬────┘        └────┬─────┘   └─────┬─────┘
        │                  │                   │              │
        └──────────────────┴─────────┬─────────┴──────────────┘
                                     │
        ┌────────────────────────────┼────────────────────────────┐
        │  Governance & Observability (cross-cutting — every op)   │
        │  audit · RBAC · retention · encryption · traces · metrics│
        └────────────────────────────┬────────────────────────────┘
                                     ▼
              ┌─────────────────────────────┐
              │         omem.core           │  ← private engine
              │  engine · brain · graph     │     (internal: BrainTrace**)
              │  retrieval · utils          │
              └─────────────────────────────┘
                            │
         ┌──────────────────┼──────────────────┐
         ▼                  ▼                  ▼
    omem.backends      omem.cloud         rust/ (PyO3)
    sqlite · postgres   client · server    SIMD scoring
```

\*\* **FLAG:** confirm whether “BrainTrace” is the committed public name.

---

## Product layers + cross-cutting concerns

Governance and Observability are **not** “Layer 5 / Layer 6 stacked after Knowledge.”
They wrap every product-layer operation.

| Kind | Package | Responsibility | Key verbs |
|------|---------|----------------|-----------|
| **Product — Memory** | `omem.memory` | Facts, experiences, preferences | `remember`, `recall`, `consolidate`, `forget` |
| **Product — State** | `omem.state` | Goals, plans, tool outputs, checkpoints | `save`, `snapshot`, `rollback`, `fork` |
| **Product — Context** | `omem.context` | Token-budget LLM input assembly | `build`, `estimate_savings` |
| **Product — Knowledge** | `omem.knowledge` | Entity graph, reasoning; *optional AST/codebase index* \* | `link`, `query`, `reason`, `ingest` |
| **Cross-cutting — Observe** | `omem.observe` | Traces, replay, cost, dashboard | `trace`, `metrics`, `replay` |
| **Cross-cutting — Governance** | `omem.governance` | RBAC, retention, audit, encryption | `set_policy`, `audit`, `delete_scope` |

\* **FLAG — confirm scope:** “AST codebase index” under Knowledge — keep in customer docs, drop, or reword to “codebase cognition”?

### Layer extensions (same package family)

| Extension | Location | Why here |
|-----------|----------|----------|
| Org memory (namespace hierarchy) | `omem.memory.org` | Scoped recall is a memory concern |
| Project / codebase cognition | `omem.knowledge.codebase` | Code symbols are a knowledge subgraph (**AST claim — confirm**) |
| Local dashboard | `omem.observe.dashboard` | Visualization is observability |

---

## Cross-Cutting Packages

| Package | Role |
|---------|------|
| `omem.provenance` | Lineage: who created what, when, with what confidence |
| `omem.runtime` | Multi-agent registry, sync, crash recovery |
| `omem.cloud` | HTTP client, remote backend, FastAPI server |
| `omem.backends` | Storage engines: SQLite, PostgreSQL, (future) cloud adapter |

---

## Private Engine (`omem.core`)

**Rule: application code never imports from `core/` directly.** Layers and `api.py` are the only callers.

```text
core/
├── engine/       BrainTrace mixins — add, RAG, lifecycle, maintenance
├── brain/        Cognitive heuristics — dream, forget, TMS, classify, secrets
├── graph/        Knowledge + causal + dependency substrates
├── retrieval/    Vector index, fusion, ranker, embeddings
└── utils/        Metrics, logging, retry, snapshots, concurrency
```

The Rust extension (`omem_rust`) accelerates batch scoring inside retrieval/brain. Rebuild with `pip install -e .` after Rust changes.

---

## Public Entry Points

```python
# Recommended — full product
from omem import AgentState

# Layer-specific (advanced)
from omem.memory import MemoryOS
from omem.state import StateOS
from omem.context import ContextEngine
from omem.knowledge import KnowledgeOS
from omem.observe import ObserveOS
from omem.governance import GovernanceOS

# Stable v1 (forever compatible)
from omem import OMem
```

Top-level modules that are **not** layers:

| Module | Role |
|--------|------|
| `agent_state.py` | Product facade composing all layers |
| `agent_config.py` | Validated config (env, dict, kwargs) |
| `api.py` | v1 `OMem` SDK |
| `cli.py` | `omem` CLI entrypoint |
| `types.py` | Shared public contracts |

---

## Dependency Rules

Layers may depend **downward** only:

```text
context  →  memory, state, knowledge
knowledge  →  memory (via OMem)
observe  →  any layer (read-only instrumentation)
governance  →  memory, state (policy enforcement)
runtime  →  memory, state
provenance  →  memory, state, knowledge

core  →  backends, rust
layers  →  core (via facades), never each other's internals
integrations  →  public API only
```

**Forbidden:** `core/` importing from layer packages. **Forbidden:** circular imports between layers.

---

## Storage Topology

```text
Local mode (default)
  ~/.omem/brain.db     — memories + graph + state tables
  ~/.omem/audit.db     — governance audit trail (WAL)

Cloud mode
  OMEM_ENDPOINT        — remote State API
  OMEM_API_KEY         — tenant auth
  Postgres + object storage (managed by OMem Cloud)
```

---

## Security Model

| Concern | Location | Notes |
|---------|----------|-------|
| Field encryption (AES-256-GCM) | `governance/encryption.py` | Opt-in via `secure` extra |
| Audit trail | `governance/audit.py` | Async, non-blocking WAL SQLite |
| Secret detection | `core/brain/secrets.py` | Blocks API keys before shared storage |
| RBAC roles | `governance/layer.py` | Local: definitions only; cloud: gateway-enforced |
| Retention / deletion | `governance/layer.py` | Cascade across memory + state + audit |

All security modules live under `governance/`. Legacy paths (`omem.security`, `omem.org`, etc.) raise `ImportError` in v3.0 — see ADR-003.

---

## Where Does New Code Go?

```text
New memory behavior (scoring, forgetting)     → core/brain/ or core/engine/
New retrieval algorithm                       → core/retrieval/ or rust/
New public memory API                         → memory/layer.py
New state checkpoint semantics                → state/
New context packing strategy                  → context/
New graph edge type                           → core/graph/ + knowledge/layer.py
New MCP tool                                  → integrations/
New cloud route                               → cloud/routes/ (when split)
New benchmark                                 → benchmarks/ or eval/ (dev-only)
New integration adapter                       → integrations/
```

When unsure: **extend the layer facade, delegate to core.**

---

## Package Tree (canonical)

```text
omem/
├── agent_state.py              # Product facade
├── agent_config.py             # Configuration
├── api.py                      # v1 OMem (stable)
├── cli.py                      # CLI
├── types.py                    # Shared contracts
│
├── memory/                     # Layer 1
│   ├── layer.py                # MemoryOS
│   └── org/                    # Namespace hierarchy + scoped recall
├── state/                      # Layer 2
├── context/                    # Layer 3
├── knowledge/                  # Layer 4
│   └── codebase/               # Project Memory (AST + code graph)
├── observe/                    # Layer 5
│   ├── events.py               # Traces, replay, OTLP
│   └── dashboard/              # Local web UI
├── governance/                 # Layer 6
│   ├── layer.py                # Policies, RBAC, deletion
│   ├── audit.py                # Audit trail
│   └── encryption.py           # Field-level encryption
├── provenance/                 # Lineage
├── runtime/                    # Multi-agent coordination
├── cloud/                      # Client + server
├── backends/                   # sqlite | postgres
├── core/                       # Private engine
└── integrations/               # MCP, LangChain, CrewAI, LlamaIndex
```

Guard modules at package root (raise `ImportError` with migration hints — not importable):
`org.py`, `security.py`, `codebase.py`, `viz.py`, `classify.py`

Dev-only (not product layers): `benchmarks/eval/`, `benchmarks/`, `examples/`, `tests/`.

---

## Cloud Roadmap (structure target)

```text
cloud/
├── client.py           # OMemCloudClient
├── backend.py          # CloudBackend (implements backends.Backend)
├── server.py           # App factory (thin)
├── routes/             # memory, state, context, knowledge, runtime
├── middleware/         # auth, tenancy, rate limits
└── models/             # Pydantic request/response schemas
```

Current state: monolithic `server.py`. Split when Cloud C2–C3 land.

---

## Related Documents

- [ADR-001: Facade Pattern](./adr/001-facade-pattern.md)
- [ADR-002: Canonical Package Layout](./adr/002-canonical-package-layout.md)
- [ADR-003: v3.0 Release](./adr/003-v3-release.md)
- [Project Structure](./PROJECT_STRUCTURE.md) — contributor quick reference
- [Full Implementation Plan](../roadmap/FULL_IMPLEMENTATION_PLAN.md) — phased delivery
