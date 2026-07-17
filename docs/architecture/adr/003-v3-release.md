# ADR-003: "v3" Architecture — Package Consolidation

**Status:** Accepted (architecture merged; **not yet released** — ships in 0.0.3)
**Date:** 2026-06-25

> **Naming note:** "v3" here refers to the third internal architecture
> iteration, not a published package version. The package version line is
> 0.0.x; the latest published release is 0.0.1 (PyPI) / v0.0.2 (GitHub).

---

## Context

v2 shipped the six-layer architecture (`memory`, `state`, `context`, `knowledge`, `observe`, `governance`) plus cross-cutting packages, while retaining backward-compat shims for pre-v2 import paths (ADR-002).

Maintaining dual paths increased contributor confusion, duplicated package surface area, and delayed the clean mental model: **one tree, one rule for where code belongs**.

## Decision

Ship the consolidated package layout (in release 0.0.3) with the following
breaking changes.

### Removed modules

Legacy **package directories** were deleted. Single-file guard modules (`omem/org.py`, etc.) remain so that accidental imports fail immediately with a migration message instead of resolving to empty namespace packages:

| Legacy import | v3.0 behavior | Use instead |
|---------------|---------------|-------------|
| `omem.org` | `ImportError` | `omem.memory.org` |
| `omem.security` | `ImportError` | `omem.governance` |
| `omem.codebase` | `ImportError` | `omem.knowledge.codebase` |
| `omem.viz` | `ImportError` | `omem.observe.dashboard` |
| `omem.classify` | `ImportError` | `omem.core.brain.classify` |

### Unchanged (no migration required)

```python
from omem import AgentState, OMem, OrgMemoryOS, MemoryOS, GovernanceOS
```

Top-level `omem.__all__` exports are stable. Only **deep import paths** changed.

### Repo layout changes (non-breaking for pip users)

- Root `Dockerfile` / `docker-compose.yml` removed → use `deploy/docker/`
- `issues/` → `docs/ideas/`
- Eval harness → `benchmarks/eval/`

## Migration checklist

```bash
# 1. Search your codebase for legacy imports
rg 'omem\.(org|security|codebase|viz|classify)' .

# 2. Replace using the table above

# 3. Upgrade (once 0.0.3 is published)
pip install -U "omem-os>=0.0.3"

# 4. Verify
pytest tests/test_import_compat.py -k canonical
```

## Version policy going forward

| Major | When |
|-------|------|
| v3.x | Six-layer layout locked; no new top-level `omem/` packages without ADR |
| v4.x | Reserved for cloud API surface (`cloud/routes/` split) or storage protocol changes |

## Consequences

**Good:**

- Zero ambiguity in package tree
- Security, org memory, codebase, dashboard live in their logical layers
- Smaller installed package (fewer re-export modules)

**Breaking:**

- Any code importing removed shim paths must update imports
- Downstream forks referencing old paths in docs need a one-time fix

## Compliance

- [x] All 733+ tests pass with shims removed
- [x] `test_v3_legacy_shim_paths_raise_import_error` guards against regression
- [x] CHANGELOG documents breaking changes
- [x] ARCHITECTURE.md reflects final tree
