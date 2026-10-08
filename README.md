# OMem

**The durable state layer for production AI agents.**

Persist. Recover. Replay. Fork. Context. Audit.

Not a vector DB. Not an agent framework. Not Temporal. Framework-neutral history + checkpoints so agents can die without losing work.

Tech preview — not GA. Not SOC2.

## Quick proof

```bash
pip install omem-os
OMEM_EMBEDDER=hash omem demo kill-resume
```

```python
from omem import AgentState

agent = AgentState(session_id="incident-agent", backend="memory")
run = agent.start_run(goal="Investigate outage")
run.record("tool_call", {"tool": "logs.query"}, idempotency_key="logs:1")
ck = run.checkpoint()
# process dies → new process:
run = agent.resume_run(run.run_id)  # Mode A: checkpoint-assisted resume
```

## Design partners

Eval pack: [docs/design-partner/](./docs/design-partner/README.md)

```bash
OMEM_EMBEDDER=hash omem demo poison-recovery   # governance / rollback
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
| Audit | `agent.governance.export_audit` / `omem governance audit` |
| Cloud | Multi-tenant API + Postgres RLS — sibling `omem-cloud` (tech preview) |
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

- [Developer guide](./docs/guides/DEVELOPER.md) — install, API, CLI
- [MCP setup](./docs/guides/MCP_SETUP.md) — Cursor / Claude / OpenCode (local)
- [Personal MCP](./docs/guides/PERSONAL_MCP.md) — shared memory across agents
- [Design partners](./docs/design-partner/README.md)
- [Docs index](./docs/README.md) · [Limits](./docs/LIMITATIONS.md)
- [Versioning](./docs/guides/VERSIONING.md) · [Releasing](./docs/guides/RELEASING.md)

## License

MIT — [LICENSE](./LICENSE)
