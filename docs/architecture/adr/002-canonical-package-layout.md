# ADR-002: Canonical Package Layout

**Status:** Implemented (v3.0)  
**Date:** 2026-06-25  
**Completed:** 2026-06-25  

---

## Context

OMem shipped v2 layer facades alongside legacy packages that violated the six-layer model. ADR-002 defined canonical locations and temporary v2.x shims.

## Decision

See [ADR-003](./003-v3-release.md) for the v3.0 completion. All code now lives at canonical paths; shims are removed.

### Canonical locations (final)

| Former path (removed v3.0) | Canonical path | Layer |
|----------------------------|----------------|-------|
| `omem/security/` | `omem/governance/` | 6 — Governance |
| `omem/org/` | `omem/memory/org/` | 1 — Memory |
| `omem/codebase/` | `omem/knowledge/codebase/` | 4 — Knowledge |
| `omem/viz/` | `omem/observe/dashboard/` | 5 — Observe |
| `omem/classify.py` | `omem/core/brain/classify.py` | core |

### Required imports (v3.0+)

```python
from omem.governance.audit import AuditLogger
from omem.governance.encryption import EncryptionManager
from omem.memory.org import OrgMemoryOS
from omem.knowledge.codebase import ProjectGraph
from omem.observe.dashboard import serve
from omem.core.brain.classify import auto_classify
```

## Compliance

- [x] Shims removed in v3.0
- [x] All tests use canonical paths
- [x] `from omem import AgentState, OrgMemoryOS, …` unchanged at top level
- [ ] Cloud package split — separate ADR when C2 ships
