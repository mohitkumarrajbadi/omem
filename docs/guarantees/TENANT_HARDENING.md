# Tenant hardening & governance guarantees

**Audience:** design-partner security / platform reviewers  
**Status:** tech preview (July 2026)

This document states what OMem **guarantees today** in OSS, and what it
**does not**. Prefer this over reading architecture diagrams alone.

## Guarantees (local OSS)

| Guarantee | Mechanism | Proof |
|-----------|-----------|-------|
| Client cannot rewrite org via namespace string | `harden_namespace()` ignores client org/workspace prefix unless `trust_client_suffix` is opt-in for a relative suffix | `tests/test_memory_os_charter.py` |
| Field encryption when key present | AES-256-GCM on `content` + `metadata` (`ENC:v1:` prefix) | `tests/test_encryption_e2e.py` |
| Audit trail query + export | Async WAL SQLite audit DB; `export_audit(json\|jsonl)` | `GovernanceOS.export_audit`, CLI `--format` |
| Content-hash memory IDs scoped by org+namespace | Idempotent writes / dedup | Architecture charter tests |
| Retention policies enforceable locally | `set_policy` + `enforce_retention` | Governance layer |

## Explicit non-guarantees (today)

| Non-guarantee | Reality | Roadmap |
|---------------|---------|---------|
| Local RBAC is not an authorization gate | Roles are registered and queryable; OSS does **not** block calls | Cloud gateway enforcement (omem-cloud) |
| Postgres RLS | Lives in omem-cloud multi-tenant path, not default SQLite OSS | Cloud design partners |
| SOC2 / ISO certs | **Not yet started** for OMem Cloud Type I evidence collection; none claimed for OSS | Start formal track only when design-partner bar requires it |
| Multi-node HA/DR | Single-node WAL + WriteBuffer crash recovery only | 6-month cloud plan |
| Vectors encrypted | Intentionally plaintext for ANN | Documented trade-off |
| Audit cascade counts | `DeletionReport.deleted_audit_entries` may under-count | Tracked hardening |

## Threat model (narrow)

**In scope for this preview:** confused-deputy namespace spoofing from a
client-supplied header/string; plaintext disk content when encryption is
enabled; retention/deletion for a design-partner POC.

**Out of scope:** full zero-trust sidecars, KMS key rotation UX, cross-region
replication, LLM prompt injection, model-provider data retention.

## Recommended partner acceptance tests

1. Attempt `harden_namespace("other-org/...", binding)` → must resolve under
   binding org.
2. With `OMEM_ENCRYPTION_KEY` set, inspect raw SQLite → no plaintext secrets.
3. Export audit JSON after remember/recall/delete → entries present and filterable.
4. Enforce a 0-day retention policy in a throwaway namespace → memories evicted.

## Contact framing

Describe deployments as **design-partner tech preview** until HA/DR and
encryption E2E stories match your production bar. That framing is intentional —
it survives diligence better than premature GA language.
