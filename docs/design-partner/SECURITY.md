# Security controls

## Guaranteed in product today

| Control | Where |
|---------|--------|
| AES-256-GCM field encryption | OSS + Cloud (`OMEM_ENCRYPTION_KEY`) |
| Snapshot / rollback | OSS + Cloud |
| Audit export | OSS + Cloud |
| Fail-closed tenant RLS | Cloud Postgres (`omem_app`, migrations 012+) |
| API key rotation + grace | Cloud admin API |

## Not claimed yet

- Completed SOC2 Type I/II  
- Cloud GA / SLA  
- Experimental AST index as a product feature  

## Verify

```bash
OMEM_EMBEDDER=hash omem demo poison-recovery
```

Cloud operator gates: `omem-cloud/docs/deployment/GA_HARDENING.md`
