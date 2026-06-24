# ADR-001: V2 Facade Pattern

**Status:** Accepted  
**Date:** 2026-06-24  
**Author:** OMem core team

---

## Context

OMem v1 shipped a mature `OMem` API backed by `BrainTrace`. It has tests,
examples, and live integrations (MCP, LangChain, CrewAI). Users depend on it.

The v2 direction repositions OMem as **Persistent State Infrastructure**
with six layers: memory, state, context, knowledge, observability, and
governance. This requires new public packages (`omem.state`, `omem.context`,
etc.) without breaking the stable v1 surface.

## Decision

All v2 layers are implemented as **thin facades** over the existing engine:

1. Each v2 package lives in `omem/{layer}/` with a `layer.py` module.
2. Every facade delegates to `BrainTrace` / `OMem` internals — no logic
   is duplicated in the facade layer.
3. The `OMem` class in `omem/api.py` remains unchanged and stable.
4. A new `AgentState` class in `omem/agent_state.py` composes all facades
   into the single developer-facing product object.
5. Stubs raise `NotImplementedError` until each phase is implemented,
   so the full interface is always visible and type-checkable.

## Package map

| v2 package | Implementation phase | Delegates to |
|------------|---------------------|-------------|
| `omem.memory` | Done (v2 MemoryOS) | `OMem` |
| `omem.state` | Phase 2 | new SQLite/Postgres tables |
| `omem.context` | Phase 3 | `rag.py` + `ranker.py` + `StateOS` |
| `omem.knowledge` | Phase 4 | `core/graph/knowledge.py` |
| `omem.observe` | Phase 6 | `core/utils/metrics.py` + new trace tables |
| `omem.governance` | Phase 8 | `security/audit.py` + `brain/quotas.py` |
| `omem.provenance` | Phase 7 | `types.Provenance` + new lineage tables |
| `omem.runtime` | Phase 9 | new agent registry + scheduler hooks |
| `omem.cloud` | Cloud C1–C5 | HTTP adapter + FastAPI service |

## Consequences

**Good:**
- Zero breaking changes for existing users (`from omem import OMem` still works).
- Contributors know exactly where to add Phase 2+ work.
- The full v2 API surface is visible and type-checkable from Day 1.
- `AgentState` is the single import for new users.

**Trade-off:**
- Stub `NotImplementedError` methods require discipline — every new phase
  must replace stubs with real code and tests before merging.
- Two public entry points (`OMem` and `AgentState`) exist during the transition.
  `OMem` will be deprecated (not removed) once Phase 5 is complete.

## Compatibility policy

- `OMem`, `Memory`, `MemoryType`, `MemoryTier`, `MemoryLevel`, `MemoryPriority`,
  `RetrievalExplanation` — **stable**, no breaking changes in v2.x.
- `MemoryOS`, `MemoryQuery` — **stable** as of v2 MemoryOS launch.
- `AgentState` — **unstable** until Phase 5 is complete; may change.
- All other v2 layer classes — **unstable** until their phase ships.
