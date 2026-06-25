# ADR-002: Canonical Package Layout

**Status:** Accepted  
**Date:** 2026-06-25  
**Supersedes:** scattered placement in `PROJECT_STRUCTURE.md` (pre-v2 orphans)

---

## Context

OMem shipped v2 layer facades (memory through runtime) alongside legacy packages:

- `security/` — audit + encryption (predates governance layer)
- `org/` — org memory (Phase 10, absent from end-state diagram)
- `codebase/` — project memory (parallel to knowledge layer)
- `viz/` — dashboard (parallel to observe layer)
- `classify.py` — ingestion helper at package root

Five top-level orphans violated the six-layer model and confused contributors about where new code belongs.

## Decision

### 1. Canonical locations

| Former path | Canonical path | Layer |
|-------------|----------------|-------|
| `omem/security/audit.py` | `omem/governance/audit.py` | 6 — Governance |
| `omem/security/encryption.py` | `omem/governance/encryption.py` | 6 — Governance |
| `omem/org/` | `omem/memory/org/` | 1 — Memory (extension) |
| `omem/codebase/` | `omem/knowledge/codebase/` | 4 — Knowledge (extension) |
| `omem/viz/server.py` | `omem/observe/dashboard/server.py` | 5 — Observe (extension) |
| `omem/classify.py` | `omem/core/brain/classify.py` | core (ingestion) |

### 2. Backward compatibility

Each former path remains as a **thin re-export shim** with a deprecation docstring. No breaking import changes in v2.x.

Shims will be removed in v3.0 with a documented migration window.

### 3. Layer extension pattern

Features that belong to a layer but are optional sub-domains use a sub-package:

```text
memory/org/           # not a seventh layer
knowledge/codebase/   # not a separate product surface
observe/dashboard/    # not a separate CLI package
```

Public exports are promoted through the parent layer's `__init__.py` where appropriate.

### 4. What stays at package root

Only durable product boundaries:

- `agent_state.py`, `agent_config.py` — product facade + config
- `api.py` — v1 stable SDK
- `cli.py`, `types.py` — entrypoint + contracts

Everything else is a layer, cross-cutting package, integration, or deprecated shim.

## Consequences

**Good:**

- Single mental model: six layers + cross-cutting + core
- Security colocated with governance (policy + audit + encryption)
- Org memory correctly nested under memory (namespace scoping)
- Codebase cognition nested under knowledge (graph subdomain)
- Dashboard nested under observe (visualization = observability)

**Trade-offs:**

- Temporary shim packages add import indirection until v3.0
- `from omem import OrgMemoryOS` still works via `memory.org` re-export chain
- Contributors must read `ARCHITECTURE.md` before adding top-level modules

## Migration guide (for contributors)

```python
# Old (still works)                    # New (preferred)
from omem.security.audit import ...    from omem.governance.audit import ...
from omem.org import OrgMemoryOS        from omem.memory.org import OrgMemoryOS
from omem.codebase import ...          from omem.knowledge.codebase import ...
from omem.viz.server import serve       from omem.observe.dashboard import serve
from omem.classify import ...          from omem.core.brain.classify import ...
```

## Compliance

- [x] All existing tests pass with shims
- [x] `from omem import *` public surface unchanged
- [x] ADR-001 facade delegation rules unchanged
- [ ] Cloud package split (`routes/`, `middleware/`) — separate ADR when C2 ships
