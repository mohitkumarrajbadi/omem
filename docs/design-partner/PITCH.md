# OMem — one-pager

**OMem Labs** · Winter 2027 · **Tech preview — not GA**

## Line

Audit & rollback layer for AI agents.

## Problem

Vector memory is commoditizing. Regulated agent deploys stall on **prove, isolate, erase, roll back** — a security/platform budget, not “cheaper tokens.”

## Product

- **omem-os** — governed memory, snapshot/rollback, AES-256-GCM, audit export, MCP  
- **omem-cloud** — multi-tenant API, Postgres RLS, key rotation, Governance console  
- **GovernedMem0** — keep Mem0 retrieval; wrap writes/erasure in OMem audit  

## Proof

```bash
OMEM_EMBEDDER=hash omem demo poison-recovery
```

Poison → provenance → rollback + delete → audit. Cloud: fail-closed RLS.

## Not claiming

SOC2 done · Cloud GA · Better recall than Mem0 as the pitch.

## Ask

1 design partner on audit / tenant / erasure. Full pack: [docs/yc/](../yc/README.md).
