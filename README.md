# OMem

**The durable state layer for production AI agents.**

Persist. Recover. Replay. Fork. Context. Audit.

Not a vector DB. Not an agent framework. Not Temporal. Framework-neutral history + checkpoints so agents can die without losing work.

Tech preview — not GA. Not SOC2.

## Install (one command)

**macOS / Linux**

```bash
curl -fsSL https://raw.githubusercontent.com/mohitkumarrajbadi/omem/main/scripts/install.sh | bash
# wire Cursor MCP:
curl -fsSL https://raw.githubusercontent.com/mohitkumarrajbadi/omem/main/scripts/install.sh | bash -s -- --cursor
```

**Windows (PowerShell)**

```powershell
irm https://raw.githubusercontent.com/mohitkumarrajbadi/omem/main/scripts/install.ps1 | iex
```

**Or with uv** (best if you already have it)

```bash
uv tool install 'omem-os[mcp]'
omem init --cursor
```

The installer uses an isolated venv under `~/.omem/venv`, skips flaky Rust source builds by default (`OMEM_PURE_PYTHON=1`), and puts `omem` on your PATH. Prefer **Python 3.11–3.13** (prebuilt wheels). If bare `pip install` fails on Homebrew/system Python, use the curl installer — do not fight `externally-managed-environment`.

## Quick proof

```bash
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

## Install options

| Method | When |
|--------|------|
| **curl / irm installer** (above) | Default for Mac / Windows / Linux |
| `uv tool install 'omem-os[mcp]'` | You already use uv |
| `OMEM_PURE_PYTHON=1 pip install 'omem-os[mcp]'` | Inside your own venv |
| Extras | `omem-os[secure]`, `[postgres]`, `[mem0]`, `[embeddings]` |

```bash
git clone https://github.com/mohitkumarrajbadi/omem
cd omem && python3 -m venv .venv && source .venv/bin/activate
OMEM_PURE_PYTHON=1 pip install -e ".[mcp,dev]" && pytest tests/ -q
```

**pip troubleshooting:** use a venv (not system Python); prefer 3.12; set `OMEM_PURE_PYTHON=1` if a local Rust toolchain breaks the sdist build. Full guide: [docs/guides/INSTALL.md](./docs/guides/INSTALL.md).

## Docs

- [Developer guide](./docs/guides/DEVELOPER.md) — install, API, CLI
- [MCP setup](./docs/guides/MCP_SETUP.md) — Cursor / Claude / OpenCode (local)
- [Personal MCP](./docs/guides/PERSONAL_MCP.md) — shared memory across agents
- [Design partners](./docs/design-partner/README.md)
- [Docs index](./docs/README.md) · [Limits](./docs/LIMITATIONS.md)
- [Versioning](./docs/guides/VERSIONING.md) · [Releasing](./docs/guides/RELEASING.md)

## License

MIT — [LICENSE](./LICENSE)
