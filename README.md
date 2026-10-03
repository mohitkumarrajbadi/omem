<div align="center">

[![PyPI](https://img.shields.io/pypi/v/omem-os?style=for-the-badge&color=brightgreen)](https://pypi.org/project/omem-os/)
[![CI](https://img.shields.io/github/actions/workflow/status/mohitkumarrajbadi/omem/ci.yml?branch=main&style=for-the-badge)](https://github.com/mohitkumarrajbadi/omem/actions)
[![License](https://img.shields.io/badge/license-MIT-green?style=for-the-badge)](./LICENSE)

# OMem

### Audit & rollback layer for AI agents

Prove what the agent knew. Roll it back. Export the trail. Isolate tenants.

**Not another Mem0.** Keep your vector store if you have one. Use OMem when you need governance.

[5-minute demo](./docs/yc/DEMO.md) · [YC / partner pack](./docs/yc/README.md) · [Limits](./docs/LIMITATIONS.md)

</div>

---

## Who

CISOs, platform architects, compliance — EU AI Act, provenance, erasure, isolation.

> *Prove what the agent knew at time T. Show who wrote it. Show Org A cannot read Org B.*

---

## Quickstart

```bash
pip install omem-os
OMEM_EMBEDDER=hash omem demo poison-recovery   # the wedge
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
omem init --cursor    # MCP into Cursor
```

Optional: `pip install "omem-os[mem0]"` → `GovernedMem0` wraps Mem0 with OMem audit.

---

## Controls

| Control | OMem |
|---------|------|
| AES-256-GCM | `OMEM_ENCRYPTION_KEY` |
| Snapshot / rollback | `snapshot` · `rollback` · `fork` |
| Audit | `governance.export_audit` / CLI JSON |
| Tenant RLS | **OMem Cloud** (Postgres, fail-closed) |
| Key rotation | **OMem Cloud** admin API + console |
| AST code index | Alpha — off (`OMEM_ENABLE_EXPERIMENTAL_AST=1`) |

Cloud = design-partner **tech preview**, not GA → [omem-cloud](../omem-cloud/) · [GA runbook](../omem-cloud/docs/deployment/GA_HARDENING.md)

---

## Install

```bash
pip install omem-os
pip install "omem-os[mcp]"
pip install "omem-os[secure]"     # encryption
pip install "omem-os[postgres]"
pip install "omem-os[mem0]"       # GovernedMem0
```

```bash
git clone https://github.com/mohitkumarrajbadi/omem
cd omem && pip install -e ".[dev]" && pytest tests/ -q
```

---

## License

MIT — see [LICENSE](./LICENSE).
