# OMem

**Governed memory and state for AI agents** — audit, rollback, encryption, tenant isolation.

Not another vector store. Prove what the agent knew, roll it back, export the trail.

```bash
pip install omem-os
OMEM_EMBEDDER=hash omem demo poison-recovery
```

```python
from omem import AgentState

with AgentState(session_id="payments-agent") as agent:
    agent.remember("Wire beneficiary is acct-100")
    snap = agent.snapshot(label="before-tool-call")
    agent.rollback(snap.id)
    print(agent.governance.export_audit(format="json"))
```

```bash
pip install "omem-os[mcp]"
omem init --cursor
```

## Controls

| | |
|--|--|
| Encryption | AES-256-GCM via `OMEM_ENCRYPTION_KEY` |
| State | `snapshot` · `rollback` · `fork` |
| Audit | `governance.export_audit` / `omem governance audit` |
| Cloud | Multi-tenant API + Postgres RLS — [omem-cloud](../omem-cloud/) (tech preview) |
| Mem0 wrap | `pip install "omem-os[mem0]"` → `GovernedMem0` |

## Install

```bash
pip install omem-os
pip install "omem-os[mcp]"
pip install "omem-os[secure]"
pip install "omem-os[postgres]"
pip install "omem-os[mem0]"
```

```bash
git clone https://github.com/mohitkumarrajbadi/omem
cd omem && pip install -e ".[dev]" && pytest tests/ -q
```

## Docs

- [Design partners](./docs/design-partner/README.md)
- [Limits](./docs/LIMITATIONS.md)
- [Tenant hardening](./docs/guarantees/TENANT_HARDENING.md)

## License

MIT — [LICENSE](./LICENSE)
