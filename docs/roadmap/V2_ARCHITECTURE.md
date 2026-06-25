# OMem V2 Architecture Vision

## Vision

OMem v2 becomes **Persistent State Infrastructure for AI Systems** — not just a memory library.

Positioning:

```text
Agents / Apps / MCP Clients
        │
        ▼
     OMem (Agent State)
        │
        ├── Memory
        ├── State
        ├── Context
        ├── Knowledge
        ├── Observability
        ├── Governance
        └── Cloud (Akamai Agent State Cloud)
        │
        ▼
     LLMs + Storage
```

**Implementation details:** [Full Implementation Plan](./FULL_IMPLEMENTATION_PLAN.md) · [Akamai / Linode Deployment](./AKAMAI_LINODE_DEPLOYMENT.md)

## Architecture

```
omem
├── agent_state.py
├── memory          (+ org/)
├── state
├── context
├── knowledge       (+ codebase/)
├── observe         (+ dashboard/)
├── governance
├── provenance
├── runtime
├── cloud
├── backends
├── core
└── integrations
```

Dev tooling (not shipped on PyPI): `benchmarks/eval/`, `benchmarks/`, `tests/`, `examples/`.

## Layer definitions

### 1. Memory
Purpose: Store, retrieve, consolidate, forget, prioritize.

Structure:
```
omem.memory
├── Working Memory
├── Short-Term Memory
├── Long-Term Memory
├── Archive Memory
├── Consolidation Engine
├── Forgetting Engine
├── Retrieval Engine
├── Truth Maintenance
└── Memory Graph
```

APIs:
- `omem.remember()`
- `omem.recall()`
- `omem.forget()`
- `omem.consolidate()`
- `omem.explain()`

### 2. State
Purpose: Preserve execution state, not just memory.

Structure:
```
omem.state
├── Goal State
├── Plan State
├── Workflow State
├── Tool State
├── Session State
├── Agent State
├── Snapshots
├── Rollbacks
├── Forks
└── Checkpoints
```

APIs:
- `omem.state.save()`
- `omem.state.restore()`
- `omem.state.snapshot()`
- `omem.state.rollback()`
- `omem.state.fork()`
- `omem.state.checkpoint()`
- `omem.state.resume()`

### 2b. Context
Purpose: Select what actually gets sent to the LLM.

Structure:
```
omem.context
├── Context Engine
├── Token Budget Packer
├── Memory + State + Knowledge Fusion
└── Savings Metrics
```

APIs:
- `omem.context.build(task, budget_tokens)`
- `omem.context.estimate_savings()`

Without this layer: great memory, poor context.

Example state payload:
```json
{
  "goal": "Refactor auth system",
  "step": 4,
  "status": "running",
  "tool": "filesystem"
}
```

### 3. Knowledge
Purpose: Understand relationships.

Structure:
```
omem.knowledge
├── Entities
├── Relationships
├── Concepts
├── Facts
├── Graph Engine
├── Semantic Links
└── Reasoning
```

APIs:
- `omem.knowledge.link()`
- `omem.knowledge.query()`
- `omem.knowledge.reason()`

### 4. Observability
Purpose: Understand what agents are doing.

Structure:
```
omem.observe
├── Metrics
├── Traces
├── Events
├── Cost Tracking
├── Memory Metrics
├── State Metrics
├── Agent Metrics
└── Replay
```

Metrics:
- Memory Recall Rate
- Agent Success Rate
- State Recovery Rate
- Latency
- Token Usage
- Cost Savings
- Context Efficiency

APIs:
- `omem.observe.metrics()`
- `omem.observe.trace()`
- `omem.observe.replay()`

### 5. Evaluation
Purpose: Measure agent quality.

Structure:
```
omem.eval
├── Memory Bench
├── State Bench
├── Agent Bench
├── Retrieval Bench
├── Cost Bench
└── Benchmark Runner
```

Metrics:
- Recall@K
- NDCG
- State Integrity
- Workflow Recovery
- Agent Continuity
- Success Rate
- Cost Reduction

APIs:
- `omem.eval.run()`
- `omem.eval.compare()`
- `omem.eval.report()`

### 6. Governance
Purpose: Control AI systems.

Structure:
```
omem.governance
├── RBAC
├── Policies
├── Audit Logs
├── Retention
├── Deletion
├── Compliance Rules
└── Security
```

APIs:
- `omem.governance.audit()`
- `omem.governance.delete_user()`
- `omem.governance.policy()`

### 7. Provenance
Purpose: Know where information came from.

Structure:
```
omem.provenance
├── Sources
├── Lineage
├── Versions
├── History
├── Attribution
└── Confidence
```

Example provenance payload:
```json
{
  "source": "github",
  "file": "payment.py",
  "commit": "abc123",
  "timestamp": "...",
  "confidence": 0.93
}
```

APIs:
- `omem.provenance.trace()`
- `omem.provenance.history()`

### 8. Runtime
Purpose: Coordinate agents.

Structure:
```
omem.runtime
├── Agent Registry
├── Scheduler
├── Coordination
├── Message Bus
├── State Sync
└── Recovery
```

APIs:
- `omem.runtime.register()`
- `omem.runtime.sync()`
- `omem.runtime.recover()`

### 9. Integrations
Critical for adoption.

Structure:
```
omem.integrations
├── MCP
├── LangChain
├── LlamaIndex
├── CrewAI
├── OpenAI Agents
├── AutoGen
├── Claude Code
└── IDE Extensions
```

### 10. Cloud Connectors
OSS remains portable.

Structure:
```
omem.backends
├── SQLite
├── PostgreSQL
├── Redis
├── S3
├── DynamoDB
├── Qdrant
├── Weaviate
└── Neo4j
```

### 10. Cloud
Managed Agent State Cloud on Akamai / Linode.

Structure:
```
omem.cloud
├── HTTP Client
├── Remote Backend
├── FastAPI Server
├── Auth Middleware
└── Tenancy

deploy/
├── linode/terraform
├── linode/ansible
├── docker/Dockerfile.cloud
└── scripts/provision|deploy|teardown
```

Developer experience:
```bash
pip install omem
export OMEM_ENDPOINT=https://state.akamai.ai
export OMEM_API_KEY=omem_sk_...
```

See [Akamai / Linode Deployment Plan](./AKAMAI_LINODE_DEPLOYMENT.md).

## CLI structure

```
omem memory ...
omem state ...
omem context ...
omem knowledge ...
omem observe ...
omem eval ...
omem governance ...
omem provenance ...
omem runtime ...
```

## Three-tier product strategy

### OSS
Free.
Focus:
- Memory
- State
- Knowledge

### Cloud
Paid.
Focus:
- Observability
- Evaluation
- Governance

### Enterprise
High-value.
Focus:
- Compliance
- Audit
- RBAC
- Private Deployments
- Multi-Region

## Implementation roadmap

### Phase 1 — Foundation (OSS focus)
1. Build graph-first memory substrate.
2. Add state layer scaffolding.
3. Expand `types.py` for nodes/edges/evidence/provenance.
4. Extend `omem/api.py` with graph and state endpoints.
5. Evolve `dream.py` into structured consolidation and insight generation.
6. Add multi-objective retrieval with graph centrality and tier-aware scoring.

### Phase 2 — Product polish
1. Add CLI groups for memory, state, knowledge, observe, eval, governance, provenance, runtime.
2. Add observability metrics, traces, and replay support.
3. Add provenance trace/history APIs.
4. Add initial governance and audit scaffolding.

### Phase 3 — Cloud / paid differentiation
1. Build evaluation benchmarks and reporting.
2. Add richer observability and cost metrics.
3. Add governance policy engine.
4. Add private/enterprise connectors and RBAC hooks.

### Phase 4 — Enterprise moat
1. Multi-region connectors.
2. Distributed state sync and recovery.
3. Advanced runtime coordination.
4. Agent workflow orchestration.

## Repo-specific first PR scope

### Keep existing core
- `omem/api.py`
- `omem/core/engine.py`
- `omem/core/brain/dream.py`
- `omem/core/brain/forgetting.py`
- `omem/core/graph/knowledge.py`
- `omem/knowledge/codebase/retriever.py`
- `omem/cli.py`
- `omem/types.py`

### First PR tasks
1. Redesign `types.py` for graph-backed memories.
2. Harden `omem/core/graph/knowledge.py` as canonical graph store.
3. Add graph-first ingestion and state APIs to `omem/api.py`.
4. Extend `omem/core/brain/dream.py` for abstract insight creation.
5. Update `omem/core/engine/rag.py` for graph-aware scoring.
6. Add CLI scaffolding for state and knowledge.

### Second PR tasks
1. Formalize memory hierarchies and automated tier transitions.
2. Add evidence/confidence-aware forgetting and retention.
3. Create `omem/core/brain/reasoning.py`.
4. Add `observe`, `eval`, `governance` package scaffolds.

## Product positioning statement

> OMem is the AI State Infrastructure layer that provides memory, persistent state, context optimization, observability, evaluation, provenance, and governance for AI agents across sessions, workflows, and organizations.

**Cloud product:** Akamai Agent State Cloud — one endpoint, no customer-managed databases.

## Notes

This plan preserves the repository's current memory and graph strengths while shifting the narrative and architecture to become a larger AI state platform. It is intentionally designed to support an OSS-first v2 product that extends into Akamai Cloud via Linode tech preview, then paid observability and enterprise governance.

**Detailed phased delivery:** [Full Implementation Plan](./FULL_IMPLEMENTATION_PLAN.md)
