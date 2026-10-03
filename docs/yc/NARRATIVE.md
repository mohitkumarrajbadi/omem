# Narrative (frozen)

Do not invent a second story. Every README, video, and YC answer uses this.

## One-liner (≤50 chars)

`Audit & rollback layer for AI agents`

## Company

**OMem Labs** — Governed, auditable memory and state for AI agents.

## Wedge (one sentence)

Enterprises already have vector memory. They lack **proof**: what the agent knew at time T, who wrote it, that tenants are isolated, and that erasure reached agent memory.

## Not this

- Not “better Mem0 / Zep recall”
- Not an LLM product
- Not AST code search (Alpha, off by default)

## Product

| Piece | What it is | Status |
|-------|------------|--------|
| **omem-os** | Local governed memory: remember, snapshot/rollback, AES-256-GCM, audit export, MCP | Working |
| **omem-cloud** | Multi-tenant API + console: Postgres RLS, key rotation, Governance UI | Tech preview |
| **GovernedMem0** | Optional wrap: keep Mem0 retrieval, OMem audit/erasure path | Working |

## Buyer

CISO / platform / compliance — EU AI Act, internal AI policy, audit budget.  
Not hobby agent builders shopping for “more memory.”

## Proof line (honest)

> Poisoned memory → provenance → rollback + delete → audit trail.  
> Cloud: fail-closed RLS + rotatable keys. Design-partner tech preview — not GA.

## Ask

1 design partner evaluating **audit / tenant / erasure**. Then YC as acceleration — not as a substitute for a customer.
