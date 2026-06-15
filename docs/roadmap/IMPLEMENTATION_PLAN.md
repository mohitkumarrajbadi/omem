# OMem V2 Implementation Plan

This file tracks the practical implementation direction for OMem v2. The full public roadmap lives in [ROADMAP.md](./ROADMAP.md); this file is the working engineering plan.

## Current Position

OMem is no longer just an embedding table with search. The repo already includes:

- Graph-backed memory metadata: nodes, relation edges, evidence, provenance, confidence.
- Graph-first ingestion through `AddMixin.add()` and `add_experience()`.
- Multi-objective retrieval with semantic, keyword, recency, importance, confidence, graph, centrality, personalization, and frequency signals.
- A sleep cycle with forgetting, reflection, compression, and dream consolidation.
- Memory hierarchy fields and graph-aware tier scheduling.
- MCP, CLI, dashboard, examples, codebase indexing, SQLite, and PostgreSQL support.

That means the immediate v2 work should not rewrite the core. It should package the existing foundations into clear, team-owned layers and add the missing state infrastructure.

## V2 North Star

OMem becomes AI state infrastructure:

```text
Agents / Apps / MCP Clients
        |
        v
OMem
        |
        +-- Memory
        +-- State
        +-- Knowledge
        +-- Observability
        +-- Evaluation
        +-- Governance
        +-- Provenance
        +-- Runtime
        +-- Integrations
        +-- Backends
```

## Phase 0: OSS Readiness

Status: mostly done.

- [x] Rewrite README for GitHub discovery and contributor onboarding.
- [x] Add project structure guide.
- [x] Add v2 roadmap.
- [x] Add PR template.
- [x] Add v2, docs, and good-first-issue templates.
- [x] Add governance, maintainers, support, and code of conduct docs.
- [ ] Add or verify GitHub labels.
- [ ] Add social preview image.
- [ ] Pin a `What are you building with OMem?` discussion.

## Phase 1: Stabilize V2 Package Boundaries

Goal: make the repo easy for a team to extend without breaking the stable `OMem` API.

Tasks:

- [ ] Define compatibility policy for `OMem`, `Memory`, `MemoryType`, `MemoryTier`, and retrieval explanations.
- [ ] Add package-level docs for current modules.
- [ ] Decide whether new v2 namespaces start as facades over current modules:
  - `omem.memory`
  - `omem.state`
  - `omem.knowledge`
  - `omem.observe`
  - `omem.governance`
  - `omem.provenance`
  - `omem.runtime`
- [ ] Add smoke tests proving old imports still work.
- [ ] Add architecture decision records for major v2 choices.

Acceptance criteria:

- Contributors know where to put new work.
- Existing examples continue to pass.
- Public API compatibility is tested.

## Phase 2: State Layer

Goal: preserve agent execution state, not just memory.

Target APIs:

```python
brain.state.save(session_id, payload)
brain.state.restore(session_id)
brain.state.snapshot(session_id)
brain.state.rollback(snapshot_id)
brain.state.fork(snapshot_id)
```

Data model:

- Goal state
- Plan state
- Workflow step state
- Tool state
- Session state
- Agent state
- Snapshot metadata
- Rollback/fork lineage

Tasks:

- [ ] Add typed state dataclasses.
- [ ] Add SQLite persistence for state snapshots.
- [ ] Add in-memory backend implementation.
- [ ] Add public API facade.
- [ ] Add tests for save, restore, snapshot, rollback, fork.
- [ ] Add docs and example.

## Phase 3: Provenance and Confidence

Goal: make every important memory and state transition traceable.

Tasks:

- [ ] Normalize provenance payloads across memory, graph, state, and codebase indexing.
- [ ] Add source, timestamp, namespace, confidence, and lineage to public outputs.
- [ ] Add provenance query API.
- [ ] Track consolidation source IDs in a user-facing way.
- [ ] Add tests for provenance retention across sleep cycles.

## Phase 4: Observability

Goal: help teams understand what memory is doing for agents.

Metrics:

- Recall hit rate
- Recall latency
- Context tokens saved
- Memory freshness
- Conflict count
- Consolidation count
- State restore success rate
- Backend operation latency

Tasks:

- [ ] Add trace event schema.
- [ ] Add memory decision replay format.
- [ ] Expose metrics through SDK and CLI.
- [ ] Add dashboard panels for recall and sleep cycle metrics.
- [ ] Add benchmark report output.

## Phase 5: Governance

Goal: make production memory controllable.

Tasks:

- [ ] Add retention policy primitives.
- [ ] Add namespace deletion workflows.
- [ ] Add user deletion workflow.
- [ ] Add audit query APIs.
- [ ] Add policy-aware recall filters.
- [ ] Add tests for deletion, retention, and audit logs.

## Phase 6: Runtime Coordination

Goal: support multi-agent systems that share memory and state intentionally.

Tasks:

- [ ] Add agent registry.
- [ ] Add scheduler hooks for sleep and maintenance.
- [ ] Add namespace sharing policy.
- [ ] Add recovery hooks.
- [ ] Add MCP tools for state and runtime operations.

## High-Priority Starter Issues

- Add CSV export to CLI.
- Add `OMem.count(namespace=None)`.
- Add namespace isolation regression tests.
- Add docs recipe for Claude Desktop memory.
- Add docs recipe for codebase indexing with Cursor.
- Add benchmark report JSON output.
- Add graph query examples.
- Add LangGraph integration example.

## Quality Bar

Every v2 PR should include:

- A clear issue or roadmap link.
- Typed public contracts.
- Tests without external API calls.
- Docs or examples for user-facing behavior.
- Benchmark notes for retrieval, ingestion, lifecycle, or backend changes.
