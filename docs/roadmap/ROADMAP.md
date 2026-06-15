# OMem V2 Roadmap

OMem v2 turns the current memory library into AI state infrastructure: memory, state, knowledge, observability, evaluation, governance, provenance, runtime coordination, and integrations.

## Current Status

| Area | Status | Notes |
|---|---|---|
| Memory core | Shipped | Add, recall, sleep, inspect, compression, forgetting |
| Graph substrate | Shipped | Entities, relation edges, evidence, confidence, Graph-RAG |
| Multi-objective retrieval | Shipped | Semantic, keyword, recency, importance, confidence, graph, personalization |
| Persistence | Shipped | SQLite stable, PostgreSQL beta |
| MCP integration | Shipped | Claude Desktop and Cursor compatible server |
| Codebase memory | Alpha | Python AST indexing and graph retrieval |
| State layer | Planned | Goal, plan, session, tool, workflow snapshots |
| Observability | Planned | Traces, replay, memory metrics, context efficiency |
| Governance | Planned | Policy engine, retention, deletion, compliance workflows |
| Runtime coordination | Planned | Agent registry, scheduler, sync, recovery |

## Milestone 1: V2 Foundations

Goal: make the current system easy for teams to extend without breaking the stable API.

- Document package boundaries and contribution ownership.
- Add typed state snapshot contracts.
- Add provenance payloads to public APIs.
- Add benchmark gates for retrieval quality and latency.
- Add issue labels and roadmap issues for contributors.

## Milestone 2: State Infrastructure

Goal: preserve execution state, not just memory.

- `omem.state.save()`
- `omem.state.restore()`
- `omem.state.snapshot()`
- `omem.state.rollback()`
- `omem.state.fork()`

Target use cases:

- Long-running agent workflows
- Crash recovery
- Tool state restoration
- Branching/forking agent plans

## Milestone 3: Observability and Evaluation

Goal: let teams measure whether memory improves agent behavior.

- Recall@K and NDCG benchmark runner
- Context saved per recall
- Memory hit rate
- Agent continuity score
- Replayable traces for memory decisions
- CI-friendly benchmark reports

## Milestone 4: Governance and Provenance

Goal: make OMem safe for production systems.

- Retention policies
- Deletion workflows
- Audit trails
- Source lineage
- Confidence and evidence history
- Optional field-level encryption policies

## Milestone 5: Runtime Coordination

Goal: coordinate multiple agents around shared state safely.

- Agent registry
- Memory and state sync
- Scheduler hooks
- Recovery hooks
- Namespace and policy-aware sharing

## Contributor Lanes

| Lane | Best For | Starter Work |
|---|---|---|
| Docs and examples | First-time contributors | Add recipes, explain concepts, improve examples |
| Retrieval quality | ML/search contributors | Add ranking tests, tune fusion profiles, benchmark regressions |
| Integrations | Agent builders | Add LangGraph, AutoGen, OpenAI Agents examples |
| State layer | Backend/API contributors | Design snapshot contracts and storage adapters |
| Governance | Security/platform contributors | Add retention and deletion policy primitives |

## Definition of Done for V2 Work

- Public API is typed and documented.
- Tests run without external API calls.
- New behavior has at least one example or docs snippet.
- Backwards compatibility is preserved or the migration path is explicit.
- Performance-sensitive changes include benchmark notes.
