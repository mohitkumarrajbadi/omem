# OMem — one-pager

**Audit & rollback layer for AI agents** · Tech preview — not GA

## Problem

Agents remember. Enterprises need to **prove** what they knew, **roll back** bad beliefs, and show **who wrote** the fact.

## Product

- **omem-os** — governed memory, snapshot/rollback, AES-256-GCM, audit export, MCP  
- **omem-cloud** — multi-tenant API, Postgres RLS, key rotation (preview)  
- **GovernedMem0** — keep Mem0 retrieval; OMem audit/erasure path  

## Proof

```bash
OMEM_EMBEDDER=hash omem demo poison-recovery
```

## Not claiming

Cloud GA · completed SOC2 · “better recall than Mem0”

## Contact

https://github.com/mohitkumarrajbadi/omem
