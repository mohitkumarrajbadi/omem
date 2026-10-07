# Design partners

**Status:** tech preview — not GA.

Evaluate: prove / isolate / roll back / erase agent memory.

## One command

```bash
pip install omem-os
OMEM_EMBEDDER=hash omem demo poison-recovery
```

## Pack

| Doc | Purpose |
|-----|---------|
| [DEMO.md](./DEMO.md) | 5-minute evaluation walkthrough |
| [PITCH.md](./PITCH.md) | One-pager |
| [SECURITY.md](./SECURITY.md) | Controls and non-claims |
| [TENANT_HARDENING.md](../guarantees/TENANT_HARDENING.md) | Guarantees / non-guarantees |
| Cloud GA ops | [GA_HARDENING.md](../../../omem-cloud/docs/internal/GA_HARDENING.md) |

```bash
omem governance audit --format json --limit 100
```
