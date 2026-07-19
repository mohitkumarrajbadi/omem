# OMem — one-pager (Governed Agent Memory)

**For:** YC / design partners / internal sponsors  
**Date:** July 2026  
**Status:** OSS stable on core memory/state; cloud = design-partner tech preview

## Category

Not “another agent memory.” **Governed Agent Memory** — the layer that answers
*prove what your agent knew, when it knew it, and who’s allowed to see it*.

## Problem

Analysts converge: frameworks are good at *storing* memory and weak at
*governing* it (glossary, lineage, entity resolution, access control, audit).
Vector-only approaches are commoditizing. Regulated / enterprise agent deployers
need a different budget line (security / platform), not cheaper tokens.

## Product

OMem OSS is a local-first memory OS with **governance as architecture**:
content-hash IDs, `harden_namespace`, AES-256-GCM field encryption, retention,
audit export (JSON/JSONL), provenance, hybrid recall; optional in-process
OTLP JSON export/push (not full auto-instrumentation; HTTP-path OTel is
cloud-only / partial).

OMem Cloud (tech preview) is the managed multi-tenant path — sold as a
**Governed** tier to compliance/platform buyers. OMem Cloud's SOC2 Type I
evidence collection is **not yet started**, tracked in
[docs/guarantees/TENANT_HARDENING.md](../guarantees/TENANT_HARDENING.md).

## Proof (honest)

| Proof | Number | Caveat |
|-------|--------|--------|
| STATE-Bench | 80.6/100 | Native agent-state suites |
| LongMemEval oracle retrieval | 72.5% Hit@5 (n=40) | Not LLM-judge E2E |
| LoCoMo retrieval | 66.2% Hit@5 (n=80) | Answer or evidence |
| BEAM-style abilities | 10/10 pass | Synthetic, not official BEAM |

Pack: `docs/design-partner/` · Guarantees: `docs/guarantees/TENANT_HARDENING.md`

## Ask

1 design partner evaluating **audit / tenant / encryption** (internal OK;
external stronger). Keep all cloud claims as **tech preview** until HA/DR is
real. Then YC — as a different bet on the same category Mem0 validated, not a
clone.
