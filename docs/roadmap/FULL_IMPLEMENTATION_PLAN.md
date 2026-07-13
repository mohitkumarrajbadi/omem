# OMem Full Implementation Plan

Master engineering plan from **OSS library → Agent State Infrastructure → Akamai/Linode managed tech preview → enterprise product**.

Related docs:

- [V2 Architecture Vision](./V2_ARCHITECTURE.md) — long-term package and platform shape
- [V2 Roadmap](./ROADMAP.md) — public milestone summary
- [Implementation Plan](./IMPLEMENTATION_PLAN.md) — working engineering checklist
- [Akamai / Linode Deployment Plan](./AKAMAI_LINODE_DEPLOYMENT.md) — cloud preview infrastructure

---

## North Star

```text
Positioning:  Persistent State Infrastructure for AI Systems
Product:      Akamai Agent State Cloud (OMem Cloud)
Developer UX: pip install omem  +  export OMEM_ENDPOINT=https://state.akamai.ai
OSS hook:     Memory + State + Knowledge (local-first, zero config)
Cloud value:  Remote backend, org memory, observability, governance, continuity
```

### Strategic repositioning

| Before | After |
|--------|-------|
| Memory Lifecycle Framework | Persistent State Infrastructure for AI Systems |
| Memory-as-a-Service | Agent State Infrastructure |
| Local library + MCP | `pip install omem` + managed endpoint |
| Internal sandbox | Customer tech preview |

Memory remains **Layer 1**. State, context, and cloud are the product differentiators.

---

## Current Baseline (Do Not Rebuild)

| Already shipped | Location |
|-----------------|----------|
| Memory ingest / recall / consolidate / forget | `omem/core/engine/`, `omem/api.py` |
| Hybrid retrieval + ranker modes | `omem/core/retrieval/` |
| Knowledge graph substrate | `omem/core/graph/` |
| SQLite + Postgres backends | `omem/backends/` |
| Partial snapshots (memory only) | `omem/core/utils/snapshot.py` |
| Audit log + encryption | `omem/governance/` |
| MCP + CLI + dashboard | `omem/integrations/`, `omem/cli.py`, `omem/observe/dashboard/` |
| v2 Memory facade (started) | `omem/memory/layer.py` → `MemoryOS` |

**Rule for every phase:** extend via facades and new tables/APIs. Do not rewrite `BrainTrace`.

---

## Target Framework Architecture

### Product layers + cross-cutting model

Governance & Observability are **cross-cutting** (apply to every op), not
sequential layers after Knowledge. Package folders may still be numbered
historically as “Layer 5/6” in code comments.

```text
Product   Memory      Facts, experiences, observations, preferences
Product   State       Goals, plans, progress, tool outputs, workflow state
Product   Context     Selects optimal LLM input from memory + state + knowledge
Product   Knowledge   Entity relationships, org topology, reasoning
                      (+ AST codebase index — FLAG: confirm customer-doc scope)
Cross-cut Observe     Traces, replay, cost, recall quality
Cross-cut Governance  Audit, RBAC, retention, compliance
```

### End-state package layout

```text
omem/
├── agent_state.py          # Top-level product facade
├── memory/                 # Product — facts, experiences
├── state/                  # Product — goals, plans, tool outputs, snapshots
├── context/                # Product — optimal LLM context assembly
├── knowledge/              # Product — graph query facade
├── observe/                # Cross-cutting — metrics, traces, replay, cost
├── governance/             # Cross-cutting — RBAC, retention, compliance
├── provenance/             # Cross-cutting lineage
├── runtime/                # Multi-agent coordination
├── cloud/                  # HTTP client + remote backend + server
├── backends/               # sqlite | postgres | cloud (remote)
├── core/                   # Private engine (internal name: BrainTrace — FLAG confirm public use)
└── integrations/           # MCP, LangChain, CrewAI, etc.
```

### System diagram

```text
Agent Applications (Coding / Support / Ops / Security)
        │
        ▼
OMem SDK  (pip install omem)
  ├── omem.memory
  ├── omem.state
  ├── omem.context
  ├── omem.knowledge
  ├── omem.observe
  └── omem.governance
        │
        ├── local mode ──► SQLite (~/.omem/brain.db)
        │
        └── cloud mode ──► OMEM_ENDPOINT
                              │
                              ▼
                    OMem Cloud (Akamai / Linode)
                      ├── State API Gateway
                      ├── Tenant + RBAC
                      ├── Postgres + Object Storage
                      └── Observability
```

### Developer-facing API (target)

```python
from omem import AgentState

# Local dev (default)
state = AgentState()

# Cloud (tech preview)
state = AgentState(endpoint="https://state.akamai.ai", api_key="omem_sk_...")

# Layer 1 — Memory
state.memory.remember("User prefers dark mode", namespace="team/acme")

# Layer 2 — State
state.set_goal("Refactor auth module")
state.set_plan(["Audit endpoints", "Add OAuth2", "Migrate sessions"])
state.record_tool_result("filesystem", {"files_changed": 12})
checkpoint = state.snapshot()

# Layer 3 — Context
context = state.context.build(budget_tokens=6000, task="continue refactor")

# Continuity
state.rollback(checkpoint.id)
branch_b = state.fork(checkpoint.id)
```

### Environment contract (cloud mode)

```bash
pip install omem
export OMEM_ENDPOINT=https://state.akamai.ai
export OMEM_API_KEY=omem_sk_...
export OMEM_ORG=acme-corp
```

No Postgres, vector DB, Redis, or graph DB managed by the customer. Akamai runs everything.

### OSS vs Cloud vs Enterprise

| Tier | Includes |
|------|----------|
| **OSS** (`pip install omem`) | Memory, State, Knowledge, local SQLite, MCP |
| **Cloud** (Linode preview → Akamai Cloud) | Remote backend, org memory, observability, snapshots in Object Storage |
| **Enterprise** | RBAC, compliance, multi-region, private VPC, SLA |

---

## Phase Dependency Graph

```text
Phase 0-1 (Boundaries)
    │
    ▼
Phase 2 (State Engine) ──────────────────────────────┐
    │                                                 │
    ├──► Phase 3 (Context Engine)                     │
    │         │                                       │
    │         ▼                                       │
    ├──► Phase 4 (Knowledge Facade)                   │
    │         │                                       │
    │         ▼                                       │
    └──► Phase 5 (AgentState Facade) ◄────────────────┘
              │
              ├──► Phase 6 (Observability)
              ├──► Phase 7 (Provenance)
              ├──► Phase 8 (Governance)
              ├──► Phase 9 (Runtime)
              ├──► Phase 10 (Org Memory)
              │
              └──► Cloud C1-C6 (Managed Service)
                        │
                        └──► Enterprise E1-E4
```

---

# Part A — OSS / SDK Phases

---

## Phase 0 — OSS Readiness

**Duration:** Done (≈1 week cleanup remaining)  
**Goal:** Repo is contributor-ready and narrative-aligned.

| Task | Status |
|------|--------|
| README, roadmap, project structure docs | ✅ |
| `MemoryOS` v2 facade started | ✅ |
| GitHub labels, social preview, pinned discussion | ⬜ |
| Update README positioning → "Persistent State Infrastructure" | ⬜ |

**Exit criteria:** External contributor can clone, run tests, and know where to add state work.

---

## Phase 1 — Stabilize V2 Package Boundaries

**Duration:** 1–2 weeks  
**Goal:** Clear module ownership without breaking `from omem import OMem`.

### Deliverables

1. **Compatibility policy** — document stable APIs (`OMem`, `Memory`, `MemoryType`, etc.).
2. **Facade pattern ADR** — all v2 layers delegate to core; no duplicate logic.
3. **Complete `omem.memory`** — finish `MemoryOS` tests, CLI group `omem memory ...`.
4. **Scaffold empty packages** with typed stubs:
   - `omem/state/`
   - `omem/context/`
   - `omem/knowledge/` (re-export graph APIs)
   - `omem/observe/`
   - `omem/governance/`
5. **Import smoke tests** — old examples + new facades both pass.

### Files

| File | Action |
|------|--------|
| `omem/__init__.py` | Export map |
| `tests/test_import_compat.py` | New |
| `docs/architecture/adr/001-facade-pattern.md` | New ADR |

**Exit criteria:** `pytest tests/ -v` green; contributors know `omem.state` is next.

---

## Phase 2 — State Engine (Priority 1)

**Duration:** 3–4 weeks  
**Goal:** Git-like agent state — save, snapshot, rollback, fork, checkpoint, resume.

Highest-leverage phase. Fork, rollback, checkpoint, cloud demo, and continuity all depend on it.

### 2.1 Data model (`omem/types.py`)

```python
@dataclass
class StatePayload:
    session_id: str
    goal: Optional[str]
    plan: List[str]
    step: int
    status: str                    # idle | running | paused | failed | done
    workflow_state: Dict[str, Any]
    tool_outputs: List[ToolResult]
    agent_metadata: Dict[str, Any]
    namespace: str
    updated_at: float

@dataclass
class ToolResult:
    tool: str
    input: Dict[str, Any]
    output: Any
    timestamp: float
    error: Optional[str]

@dataclass
class StateSnapshot:
    id: str
    session_id: str
    parent_id: Optional[str]       # fork lineage
    label: Optional[str]
    payload: StatePayload
    memory_snapshot_ref: Optional[str]
    created_at: float

@dataclass
class StateCheckpoint:
    id: str
    session_id: str
    payload_hash: str
    lightweight: bool
    created_at: float
```

### 2.2 Storage schema

New tables in SQLite/Postgres (same DB, separate schema):

```sql
CREATE TABLE state_sessions (
    session_id   TEXT PRIMARY KEY,
    org_id       TEXT,
    namespace    TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    updated_at   REAL NOT NULL
);

CREATE TABLE state_snapshots (
    id           TEXT PRIMARY KEY,
    session_id   TEXT NOT NULL,
    parent_id    TEXT,
    label        TEXT,
    payload_json TEXT NOT NULL,
    memory_ref   TEXT,
    created_at   REAL NOT NULL
);

CREATE TABLE state_checkpoints (
    id           TEXT PRIMARY KEY,
    session_id   TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at   REAL NOT NULL
);

CREATE TABLE state_fork_lineage (
    child_session_id   TEXT PRIMARY KEY,
    parent_snapshot_id TEXT NOT NULL,
    merged_at          REAL
);
```

### 2.3 State backend interface

```python
class StateBackend(ABC):
    def save_session(self, payload: StatePayload) -> None: ...
    def load_session(self, session_id: str) -> Optional[StatePayload]: ...
    def create_snapshot(self, snapshot: StateSnapshot) -> str: ...
    def get_snapshot(self, snapshot_id: str) -> Optional[StateSnapshot]: ...
    def list_snapshots(self, session_id: str) -> List[StateSnapshot]: ...
    def create_checkpoint(self, checkpoint: StateCheckpoint) -> str: ...
    def get_checkpoint(self, checkpoint_id: str) -> Optional[StateCheckpoint]: ...
```

### 2.4 Public API (`omem/state/layer.py`)

```python
class StateOS:
    def save(self, session_id: str, payload: StatePayload) -> None: ...
    def load(self, session_id: str) -> StatePayload: ...
    def update(self, session_id: str, **fields) -> StatePayload: ...
    def set_goal(self, session_id: str, goal: str) -> None: ...
    def set_plan(self, session_id: str, plan: List[str]) -> None: ...
    def record_tool(self, session_id: str, result: ToolResult) -> None: ...
    def snapshot(self, session_id: str, label: Optional[str] = None) -> StateSnapshot: ...
    def rollback(self, snapshot_id: str) -> StatePayload: ...
    def fork(self, snapshot_id: str, new_session_id: Optional[str] = None) -> str: ...
    def checkpoint(self, session_id: str) -> str: ...
    def resume(self, checkpoint_id: str) -> StatePayload: ...
    def list_snapshots(self, session_id: str) -> List[StateSnapshot]: ...
    def merge(self, winning_session_id: str, losing_session_id: str) -> StatePayload: ...
```

### 2.5 Memory snapshot integration

Extend `omem/core/utils/snapshot.py`:

- Full snapshot = memory KV + graph + state session
- Rollback restores memory and state atomically (best-effort v1; strict transactional v2)

### 2.6 CLI

```bash
omem state save --session agent-1 --goal "Refactor auth"
omem state snapshot --session agent-1 --label "before-oauth"
omem state fork --snapshot snap-abc --session agent-1-plan-b
omem state rollback --snapshot snap-abc
omem state checkpoint --session agent-1
omem state resume --checkpoint chk-xyz
omem state list --session agent-1
```

### 2.7 Tests

| Test file | Coverage |
|-----------|----------|
| `tests/test_state_engine.py` | save/load, snapshot, rollback |
| `tests/test_state_fork.py` | fork creates independent session with lineage |
| `tests/test_state_checkpoint.py` | checkpoint/resume after simulated crash |
| `tests/test_state_memory_snapshot.py` | combined memory+state rollback |

### 2.8 Example

- `examples/agent_crash_recovery.py` — 10-step workflow, kill at step 7, resume

**Exit criteria:**

- [ ] `state.fork()` and `state.rollback()` pass tests
- [ ] Crash-recovery example runs end-to-end locally
- [ ] Demo Steps 1–3 of Akamai pitch work

---

## Phase 3 — Context Engine (Priority 2)

**Duration:** 2–3 weeks  
**Goal:** Select optimal LLM input from memory + state + knowledge within a token budget.  
**Depends on:** Phase 2

### 3.1 Data model

```python
@dataclass
class ContextRequest:
    task: str
    budget_tokens: int
    session_id: Optional[str]
    namespace: Optional[str]
    mode: str = "planning"
    include: List[str] = field(default_factory=lambda: ["memory", "state", "knowledge"])
    exclude_types: List[MemoryType] = field(default_factory=list)

@dataclass
class ContextBundle:
    text: str
    sections: Dict[str, str]
    token_count: int
    memories_used: List[str]
    state_snapshot_id: Optional[str]
    savings_vs_naive: float
```

### 3.2 Pipeline (`omem/context/engine.py`)

1. Load current `StatePayload` (goal, plan, step, recent tool outputs)
2. `recall()` top-k memories for task
3. Graph neighbors for recalled entities
4. Rank sections by relevance + recency + importance
5. Pack into token budget (greedy v1; knapsack v2)
6. Format as structured prompt block

Reuses: `ranker.py` mode profiles, `rag.py`, `StateOS.load()`.

### 3.3 API

```python
class ContextEngine:
    def build(self, request: ContextRequest) -> ContextBundle: ...
    def estimate_savings(self, request: ContextRequest) -> Dict[str, float]: ...
```

### 3.4 CLI + MCP

```bash
omem context build --task "continue refactor" --budget 6000 --session agent-1
```

MCP tool: `build_context`

### 3.5 Benchmark

- `benchmarks/context_efficiency.py` — tokens saved vs naive recall-all

**Exit criteria:**

- [ ] Measurable token savings (target: 40–70% vs dump-all)
- [ ] Demo Step 6 of Akamai pitch works

---

## Phase 4 — Knowledge Facade (Priority 3)

**Duration:** 1–2 weeks  
**Goal:** Clean public API over existing graph substrate in `omem/core/graph/`.

```python
class KnowledgeOS:
    def link(self, subject: str, predicate: str, obj: str, **kwargs) -> str: ...
    def query(self, entity: str, depth: int = 2) -> GraphSubgraph: ...
    def reason(self, question: str) -> List[InferenceResult]: ...
    def entities(self, namespace: Optional[str] = None) -> List[GraphNode]: ...
```

**Exit criteria:** Graph capabilities accessible without touching `OMem` internals.

---

## Phase 5 — AgentState Unified Facade

**Duration:** 1–2 weeks  
**Goal:** Single developer-facing object composing all layers.  
**Depends on:** Phases 1–4

```python
# omem/agent_state.py
class AgentState:
    def __init__(
        self,
        session_id: Optional[str] = None,
        endpoint: Optional[str] = None,
        api_key: Optional[str] = None,
        **kwargs,
    ): ...

    @property
    def memory(self) -> MemoryOS: ...
    @property
    def state(self) -> StateOS: ...
    @property
    def context(self) -> ContextEngine: ...
    @property
    def knowledge(self) -> KnowledgeOS: ...

    def snapshot(self, label: Optional[str] = None) -> StateSnapshot: ...
    def resume(self) -> StatePayload: ...
```

Auto-detect cloud from `OMEM_ENDPOINT` and `OMEM_API_KEY` env vars.

**Exit criteria:** One import, one object; examples use `AgentState`.

---

## Phase 6 — Observability Layer

**Duration:** 2–3 weeks  
**Goal:** Answer "why did the agent fail?" and "how much did memory save?"  
**Depends on:** Phases 2–5

### Trace event schema

```python
@dataclass
class TraceEvent:
    id: str
    session_id: str
    event_type: str    # recall | snapshot | rollback | fork | context_build | tool_record
    timestamp: float
    duration_ms: float
    payload: Dict[str, Any]
    namespace: str
```

### Metrics

| Metric | Source |
|--------|--------|
| Recall hit rate | RAG mixin |
| Recall latency p50/p99 | RAG mixin |
| Context tokens saved | ContextEngine |
| Snapshot count | StateOS |
| Restore success rate | StateOS |
| Fork depth | StateOS |
| Sleep cycle stats | lifecycle mixin |

### API

```python
class ObserveOS:
    def metrics(self, namespace: Optional[str] = None) -> Dict[str, Any]: ...
    def traces(self, session_id: str) -> List[TraceEvent]: ...
    def replay(self, session_id: str) -> Iterator[TraceEvent]: ...
    def export_otel(self) -> None: ...   # optional Phase 6b
```

### Dashboard + CLI

Extend `omem/observe/dashboard/server.py` with state timeline, context savings chart, recall quality.

```bash
omem observe metrics
omem observe traces --session agent-1
omem observe replay --session agent-1
```

**Exit criteria:** Every state transition and context build emits a trace.

---

## Phase 7 — Provenance Layer

**Duration:** 2 weeks  
**Goal:** Trace where every memory and state change came from.  
**Can parallel:** Phase 6

- Normalize `Provenance` / `Evidence` across memory, state, graph
- `provenance.trace(memory_id | snapshot_id) -> ProvenanceChain`
- `provenance.history(namespace) -> List[ProvenanceEvent]`
- Track consolidation source IDs through sleep cycles

**Exit criteria:** Full lineage queryable for any snapshot.

---

## Phase 8 — Governance Layer

**Duration:** 3–4 weeks  
**Goal:** Production-safe memory and state for enterprise pilots.  
**Depends on:** Phases 2, 6, 7

### Policy primitives

```python
@dataclass
class RetentionPolicy:
    namespace_pattern: str
    max_age_days: Optional[int]
    max_count: Optional[int]
    tier: Optional[MemoryTier]

@dataclass
class DeletionPolicy:
    scope: str           # user | namespace | org | memory_id
    cascade: bool
```

### API

```python
class GovernanceOS:
    def set_policy(self, policy: RetentionPolicy) -> None: ...
    def audit(self, **filters) -> List[AuditEntry]: ...
    def delete_scope(self, scope: str, id: str) -> DeletionReport: ...
    def enforce_retention(self) -> RetentionReport: ...
```

Builds on: `omem/governance/audit.py`, `quotas.py`, `forgetting.py`.

### RBAC (basic, cloud-ready)

```python
@dataclass
class Role:
    name: str            # admin | editor | viewer
    namespaces: List[str]
    permissions: List[str]  # read | write | delete | admin
```

Local mode: single-user. Cloud mode: enforced at API gateway.

**Exit criteria:** Namespace deletion, retention enforcement, audit query all tested.

---

## Phase 9 — Runtime Coordination

**Duration:** 3–4 weeks  
**Goal:** Multiple agents sharing state safely.  
**Depends on:** Phases 2, 8, 10

```python
class RuntimeOS:
    def register(self, agent_id: str, session_id: str, capabilities: List[str]) -> None: ...
    def sync(self, session_id: str) -> StatePayload: ...
    def recover(self, agent_id: str) -> Optional[StatePayload]: ...
    def list_agents(self, namespace: str) -> List[AgentRegistration]: ...
```

- Agent registry (in-memory + persisted)
- Scheduler hooks for sleep/maintenance per namespace
- Recovery orchestration for crashed agents
- MCP tools: `register_agent`, `recover_agent`

**Exit criteria:** Agent B reads state written by Agent A in same namespace.

---

## Phase 10 — Shared Organizational Memory

**Duration:** 2–3 weeks  
**Goal:** Knowledge compounds across agents and teams.  
**Depends on:** Phase 1, Phase 8

### Namespace hierarchy

```text
personal/{user_id}/*              → private
team/{team_id}/*                  → team-shared
org/{org_id}/*                    → org-wide
org/{org_id}/team/{team_id}/*     → team within org
```

### Features

- Namespace resolver with inheritance (recall searches up the tree)
- Write policies: personal stays local; promoted memories move to team/org
- `AgentState.share(memory_id, target_namespace)` — explicit promotion
- Recall scope: `scope="team"` searches team + org namespaces

```bash
omem memory remember "API rate limit is 100/min" --namespace org/acme
omem memory recall "rate limits" --scope team
omem memory promote mem-abc --to org/acme
```

**Exit criteria:** Demo Step 7 — Agent A writes org memory, Agent B recalls it.

---

# Part B — Cloud / Managed Service Phases

Turn the OSS SDK into **Akamai Agent State Cloud** on Linode.

---

## Cloud Phase C1 — Remote Backend Interface

**Duration:** 2 weeks  
**Depends on:** Phase 5

```python
# omem/cloud/backend.py
class CloudBackend(Backend):
    """HTTP adapter implementing Backend + StateBackend."""

# omem/cloud/client.py
class OMemCloudClient:
    def __init__(self, endpoint: str, api_key: str, org_id: str): ...
```

`AgentState()` auto-selects `CloudBackend` when `OMEM_ENDPOINT` is set.

Tests: mock HTTP server in `tests/test_cloud_backend.py` (no network in CI).

**Exit criteria:** Same Python code runs against local SQLite and mock cloud backend.

---

## Cloud Phase C2 — REST API Service

**Duration:** 3–4 weeks  
**Depends on:** Phases 2–5, C1

### Service layout

```text
omem/cloud/
├── server.py           # FastAPI app
├── routes/
│   ├── memory.py
│   ├── state.py
│   ├── context.py
│   ├── knowledge.py
│   ├── observe.py
│   └── health.py
├── middleware/
│   ├── auth.py
│   ├── tenancy.py
│   └── rate_limit.py
└── Dockerfile.cloud
```

### API surface (v1)

| Method | Path | Maps to |
|--------|------|---------|
| POST | `/v1/memory/remember` | `MemoryOS.remember()` |
| POST | `/v1/memory/recall` | `MemoryOS.recall()` |
| GET | `/v1/memory/stats` | `MemoryOS.stats()` |
| POST | `/v1/state/save` | `StateOS.save()` |
| GET | `/v1/state/{session_id}` | `StateOS.load()` |
| POST | `/v1/state/snapshot` | `StateOS.snapshot()` |
| POST | `/v1/state/rollback` | `StateOS.rollback()` |
| POST | `/v1/state/fork` | `StateOS.fork()` |
| POST | `/v1/state/checkpoint` | `StateOS.checkpoint()` |
| POST | `/v1/state/resume` | `StateOS.resume()` |
| POST | `/v1/context/build` | `ContextEngine.build()` |
| GET | `/v1/observe/metrics` | `ObserveOS.metrics()` |
| GET | `/v1/observe/traces/{session_id}` | `ObserveOS.traces()` |
| GET | `/v1/health` | Health check |

### Non-functional requirements

- Request ID on every response
- Structured JSON errors
- OpenAPI spec auto-generated
- Idempotency keys on write endpoints (v1.1)

**Exit criteria:** Full agent workflow achievable via curl against local Docker.

---

## Cloud Phase C3 — Auth & Multi-Tenancy

**Duration:** 2–3 weeks  
**Depends on:** C2

### Auth model

```text
API Key format:  omem_sk_{org}_{random}
Scopes:          read | write | admin
Key storage:     Postgres api_keys table (hashed)
```

### Tenancy schema

```sql
CREATE TABLE organizations (id TEXT PRIMARY KEY, name TEXT, plan TEXT, created_at REAL);
CREATE TABLE teams (id TEXT PRIMARY KEY, org_id TEXT, name TEXT);
CREATE TABLE api_keys (id TEXT PRIMARY KEY, org_id TEXT, key_hash TEXT, scopes TEXT, created_at REAL, expires_at REAL);
```

Every row tagged with `org_id`. Middleware injects org context into all backend calls.

Namespace enforcement:

- Org key → `org/{org_id}/*` and below
- Team key → `org/{org_id}/team/{team_id}/*`

Rate limiting: 100 req/min per key (preview tier).

**Exit criteria:** Two orgs on same deployment cannot read each other's state.

---

## Cloud Phase C4 — Linode Deployment (Tech Preview)

**Duration:** 2–3 weeks  
**Depends on:** C2, C3, Phase 6

See [Akamai / Linode Deployment Plan](./AKAMAI_LINODE_DEPLOYMENT.md) for full infrastructure details.

**Exit criteria:** `export OMEM_ENDPOINT=https://...` from laptop → agent runs against Linode.

---

## Cloud Phase C5 — SDK Cloud Mode & MCP Remote

**Duration:** 1–2 weeks  
**Depends on:** C1, C4

1. `AgentState()` auto-detects cloud from env vars
2. MCP server supports remote mode (`omem serve --endpoint ...`)
3. CLI supports `--endpoint` on all commands
4. Quickstart: "Deploy an agent in 5 minutes on Akamai"

```bash
pip install omem
export OMEM_ENDPOINT=https://state-preview.akamai.ai
export OMEM_API_KEY=omem_sk_...
omem remember "User prefers Python"
omem state snapshot --session my-agent
omem serve
```

**Exit criteria:** Claude Desktop / Cursor MCP works against cloud endpoint.

---

## Cloud Phase C6 — Tech Preview Launch

**Duration:** 3–4 weeks  
**Depends on:** C4, C5, Phases 6, 10

### Launch package

| Artifact | Purpose |
|----------|---------|
| Tech preview signup (internal) | API key provisioning |
| Getting started guide | 15-minute onboarding |
| Demo notebook | 8-step leadership demo |
| Pilot feedback form | Structured input |
| Usage dashboard | Org-level metrics |
| SLA doc (best-effort) | Preview expectations |

### Pilot integrations (pick 3)

1. MCP + Cursor
2. LangChain / LangGraph example
3. One internal Akamai agent use case

### Preview success metrics

| Metric | Target |
|--------|--------|
| Pilot teams onboarded | 3–5 |
| Agent sessions with checkpoint/resume | 50+ |
| Measured context token savings | >40% avg |
| State restore success rate | >99% |
| Uptime (preview) | >99% |

**Exit criteria:** Live demo of crash recovery + org memory + token savings on Linode.

---

# Part C — Enterprise Phases (Post-Preview)

Not required for tech preview. Defines path to full Akamai Cloud product.

---

## Enterprise Phase E1 — RBAC & Compliance

**Duration:** 6–8 weeks

- Full role hierarchy: org admin → team admin → agent → viewer
- SSO (SAML/OIDC)
- SOC2-ready audit export
- Data residency controls
- GDPR deletion workflows

---

## Enterprise Phase E2 — Multi-Region & HA

**Duration:** 8–10 weeks

- Postgres read replicas
- Object Storage cross-region snapshot replication
- API gateway in 2+ Linode regions
- Failover: state resume from nearest region
- Capacity intake for >20 entities

---

## Enterprise Phase E3 — Edge Integration (Strategic Moat)

**Duration:** ongoing

- Akamai edge workers for policy enforcement
- State-aware routing to nearest state replica
- Edge caching of hot context bundles
- DDoS protection on state API

This is the long-term "AWS/GCP don't have this" story.

---

## Enterprise Phase E4 — Billing & Productization

**Duration:** 6–8 weeks

- Usage metering (API calls, storage, tokens saved)
- Plan tiers: Free OSS / Pro Cloud / Enterprise
- Self-serve API key portal
- Akamai Cloud marketplace listing

---

# Leadership Demo Script

Eight steps that prove product value vs AWS/GCP:

1. Coding agent runs a 10-step refactor, checkpoints every 3 steps
2. Kill the process at step 7
3. `state.resume(checkpoint)` — agent continues exactly where it stopped
4. Fork two plans — run Plan A and Plan B in parallel
5. Merge winner — rollback losing branch
6. Context engine — "Without OMem: 24k tokens. With OMem: 6.2k tokens"
7. Shared memory — Agent A learns API quirk; Agent B recalls from `org/acme`
8. Audit trail — who changed what state, when, why

---

# Master Timeline

Assuming **1 primary engineer** (+ occasional contributors):

```text
Month 1          Month 2          Month 3          Month 4          Month 5+
─────────────────────────────────────────────────────────────────────────────
Phase 0-1        Phase 2          Phase 3          Phase 5
(boundaries)     (State Engine)   (Context)        (AgentState)
                                  Phase 4          Phase 6
                                  (Knowledge)      (Observe)
                                                   Phase 10
                                                   (Org Memory)

                 Cloud C1-C2                       Cloud C3-C4
                 (Backend + API)                   (Auth + Linode)

                                                   Cloud C5-C6
                                                   (SDK + Preview)

                                                                  Phase 7-9
                                                                  (Provenance,
                                                                   Governance,
                                                                   Runtime)

                                                                  Enterprise E1+
```

### Milestones

| Milestone | When | Demo-able |
|-----------|------|-----------|
| M1: State works locally | End Month 1 | fork + rollback + crash recovery |
| M2: Context saves tokens | Mid Month 2 | token savings benchmark |
| M3: AgentState unified API | End Month 2 | single-import developer UX |
| M4: Cloud API running locally | Mid Month 3 | curl-based full workflow |
| M5: Linode deployment live | End Month 3 | `OMEM_ENDPOINT` from laptop |
| M6: Tech preview launch | End Month 4 | 3 pilot teams onboarded |
| M7: Enterprise features | Month 5+ | RBAC, compliance, multi-region |

---

# Critical Path (Minimum for Linode Preview)

If only five workstreams before preview:

1. **Phase 2** — State Engine
2. **Phase 3** — Context Engine
3. **Phase 5** — `AgentState` facade
4. **Cloud C2** — FastAPI REST service
5. **Cloud C4** — Linode deployment

---

# Quality Bar (Every Phase)

Every PR must include:

1. Typed public contracts (dataclasses in `types.py` or layer module)
2. Tests without external APIs (mock cloud, in-memory backend)
3. Backwards compatibility (`from omem import OMem` still works)
4. Example or doc snippet for user-facing behavior
5. Benchmark note for retrieval, context, or lifecycle changes

---

# GitHub Issue Labels

| Label | Phases |
|-------|--------|
| `v2-state` | Phase 2 |
| `v2-context` | Phase 3 |
| `v2-cloud` | C1–C6 |
| `v2-observe` | Phase 6 |
| `v2-governance` | Phase 8 |
| `v2-enterprise` | E1–E4 |
| `good-first-issue` | Phase 1, 4, docs |

---

# Why Akamai Wins vs AWS/GCP

| AWS/GCP today | OMem Cloud |
|---------------|------------|
| Agent teams assemble 5+ services | One `OMEM_ENDPOINT` |
| No unified state fork/rollback | Git-like agent state |
| Memory siloed per agent | Org-wide compounding knowledge |
| Token costs unmanaged | Context engine with measured savings |
| Agent crash = restart from scratch | Checkpoint/resume |
| Akamai has edge + security + enterprise trust | Natural home for governed agent infra |

Akamai does not need another database. Akamai needs **Agent Infrastructure**.
