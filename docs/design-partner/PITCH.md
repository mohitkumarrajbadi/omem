# OMem — one-pager

**Durable state layer for production AI agents** · Tech preview — not GA

## Problem

Production agents lose state across workers, waste context, and cannot prove what they knew, decided, or did after a crash.

## Product

- **omem-os** — runs + append-only history, checkpoints, resume, fork, budgeted context, audit  
- **omem-cloud** — multi-tenant API, Postgres RLS, key rotation (preview)  
- Memory remains a projection/feature — not the whole product  

## Proof

```bash
OMEM_EMBEDDER=hash omem demo kill-resume
OMEM_EMBEDDER=hash omem demo poison-recovery
```

## Not claiming

Cloud GA · completed SOC2 · deterministic tool re-execution · exactly-once external side effects · “better recall than Mem0”

## Contact

https://github.com/mohitkumarrajbadi/omem
