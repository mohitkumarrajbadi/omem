# 5-minute evaluation

## Run

```bash
pip install omem-os
OMEM_EMBEDDER=hash omem demo poison-recovery
```

## What you should see

1. Baseline memory + snapshot  
2. Poisoned override injected  
3. Provenance (source, actor, trust)  
4. Rollback + soft-delete remediation  
5. Note that rollback alone does not erase the memory row  

Optional:

```bash
omem governance audit --format json --limit 20
```

## Out of scope for this eval

Experimental AST index · console Alpha tabs · recall leaderboards
