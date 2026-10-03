# Security proof (one page)

For design partners and YC. No SOC2 claim. No theater.

## What we guarantee today

| Control | Where | Proof |
|---------|--------|--------|
| Field encryption AES-256-GCM | OSS + Cloud | Set `OMEM_ENCRYPTION_KEY`; ciphertext at rest |
| Snapshot / rollback | OSS + Cloud | `agent.snapshot` / `rollback`; `omem demo poison-recovery` |
| Audit export | OSS + Cloud | `governance.export_audit` / `omem governance audit --format json` |
| Fail-closed tenant RLS | Cloud Postgres | Migrations 012+; `omem_app` `NOBYPASSRLS`; session `omem.org_id` |
| API key rotation + grace | Cloud | `POST /v1/admin/keys/{id}/rotate`; audit `auth.key.rotate` |
| Alpha isolation | OSS + Cloud | AST off unless `OMEM_ENABLE_EXPERIMENTAL_AST=1`; console GA nav default |

## What we do **not** claim yet

- SOC2 Type I/II complete  
- Cloud GA / HA/DR SLA  
- “Unhackable” agents  
- Better recall than Mem0/Zep as the selling point  

## Operator gates (Cloud)

1. `OMEM_DB_URL` = `omem_app` (not superuser)  
2. `OMEM_MIGRATION_DB_URL` = admin for DDL  
3. Schema version ≥ 13  
4. Runbook: `omem-cloud/docs/deployment/GA_HARDENING.md`

## 60-second verify

```bash
# OSS wedge
OMEM_EMBEDDER=hash omem demo poison-recovery

# Cloud RLS (needs Postgres)
# export OMEM_TEST_DB_URL=...
# pytest omem-cloud/tests/test_rls.py -q
```
