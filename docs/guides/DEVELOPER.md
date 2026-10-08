# Developer guide

Get OMem running locally, wire MCP into your coding agent, then use the Python API.
Tech preview — not GA.

| Goal | Go here |
|------|---------|
| 5-minute proof | [Quick start](#1-quick-start) |
| Cursor / Claude / OpenCode memory | [MCP setup](./MCP_SETUP.md) |
| Shared memory across agents | [Personal MCP](./PERSONAL_MCP.md) |
| Team / multi-tenant cloud | [omem-cloud MCP](../../../omem-cloud/docs/guides/MCP_SETUP.md) |
| Contribute code | [Contributing](../../CONTRIBUTING.md) |

---

## 1. Quick start

**Requires:** Python 3.10+

```bash
pip install "omem-os[mcp]"

# Durable kill/resume demo (no LLM required)
OMEM_EMBEDDER=hash omem demo kill-resume

# Governance / poison → rollback demo
OMEM_EMBEDDER=hash omem demo poison-recovery
```

Wire Cursor in one command:

```bash
omem init --cursor
# Restart Cursor → MCP panel should list `omem`
# Ask: Call mcp_status, then remember "hello from Cursor"
```

From a git checkout (editable install):

```bash
git clone https://github.com/mohitkumarrajbadi/omem
cd omem
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[mcp,dev]"
pytest tests/ -q
```

Optional stronger semantic recall (downloads a local embedding model):

```bash
pip install "omem-os[embeddings]"
# or: pip install -e ".[mcp,embeddings]"
```

---

## 2. Choose your setup

```
Local laptop (you)          Team / org (shared)
─────────────────           ───────────────────
omem-os + SQLite            omem-cloud + Postgres RLS
omem serve (stdio MCP)      HTTP /mcp + API key
docs/guides/MCP_SETUP.md    omem-cloud/docs/guides/MCP_SETUP.md
```

| | Local OSS | Cloud |
|--|-----------|-------|
| Install | `pip install "omem-os[mcp]"` | sibling `omem-cloud` + `make up` |
| Memory lives in | `~/.omem/brain.db` | Cloud Postgres (tenant-isolated) |
| MCP config | `omem serve --namespace … --db-path …` | `{ENDPOINT}/mcp` + Bearer key |
| Good for | Solo builders, Cursor daily use | Design partners, multi-user |

Do **not** point Cursor at local `brain.db` if you want cloud memory — those are different stores.

---

## 3. Python API (`AgentState`)

`AgentState` is the product entry point. One object covers memory, state, context, and knowledge.

```python
from omem import AgentState

with AgentState(session_id="incident-agent", backend="memory") as agent:
    agent.remember("Wire beneficiary is acct-100")
    agent.set_goal("Investigate outage")

    run = agent.start_run(goal="Investigate outage")
    run.record("tool_call", {"tool": "logs.query"}, idempotency_key="logs:1")
    ck = run.checkpoint()

    # New process / crash boundary:
    run = agent.resume_run(run.run_id)

    snap = agent.snapshot(label="before-tool-call")
    agent.rollback(snap.id)

    ctx = agent.build_context("what do we know about the outage?", budget_tokens=2000)
    print(ctx.text)  # token-budgeted pack for the model

    print(agent.status())
```

### Common patterns

| Need | Call |
|------|------|
| Store a fact | `agent.remember("…")` |
| Search | `agent.recall("…", k=5)` |
| Git-like save | `agent.snapshot(label="…")` / `agent.rollback(id)` |
| Crash resume | `start_run` → `checkpoint` → `resume_run` |
| Context pack | `agent.build_context(task, budget_tokens=…)` |
| Knowledge edge | `agent.learn("FastAPI", "uses", "Pydantic")` |
| Audit export | `agent.governance.export_audit(format="json")` |

### Backends

```python
# In-memory (tests)
AgentState(session_id="t", backend="memory")

# Local SQLite (default path ~/.omem/brain.db)
AgentState(session_id="ops", backend="sqlite")

# Explicit DB path
AgentState(session_id="ops", backend="sqlite", db_path="./.omem/agent.db")
```

Postgres / encryption extras:

```bash
pip install "omem-os[postgres]"
pip install "omem-os[secure]"   # AES-256-GCM via OMEM_ENCRYPTION_KEY
```

Design-partner eval: [DESIGN_PARTNER_QUICKSTART.md](./DESIGN_PARTNER_QUICKSTART.md).

### Lower-level `OMem`

`from omem import OMem` still works for raw engine access (`add` / `search` / `inspect`). Prefer `AgentState` for new code.

---

## 4. MCP in 60 seconds

```bash
pip install "omem-os[mcp]"
mkdir -p ~/.omem && chmod 700 ~/.omem
omem init --cursor          # merges into ~/.cursor/mcp.json
```

Or generate absolute-path configs for Claude Code + OpenCode + Cursor:

```bash
# from an omem-oss checkout with .venv
bash scripts/install_personal_mcp.sh
python3 scripts/mcp_personal_smoke.py   # expect: ✔ PASS
```

Then in the agent chat:

> Call `mcp_status`. Then `remember` that I prefer Python. Then `recall` preferred language.

**Critical:** every client must share the same `--namespace` and `--db-path` (use an **absolute** path — many MCP clients do not expand `~`).

Full client configs, tools, and troubleshooting → [MCP_SETUP.md](./MCP_SETUP.md).

---

## 5. CLI cheat sheet

```bash
omem init [--cursor]              # init DB + print / merge MCP config
omem health                       # exit 0 if OK
omem demo kill-resume             # primary durable-state demo
omem demo poison-recovery         # governance / rollback demo

omem remember "fact" -n personal
omem recall "query" -k 5
omem add "…"                      # alias of remember

omem serve --namespace personal --db-path "$HOME/.omem/brain.db"
omem state snapshot --session mybot --label before
omem governance audit --format json --limit 100
```

Group commands: `omem state`, `omem run`, `omem context`, `omem knowledge`, `omem agent`, `omem governance`.

```bash
omem --help
omem state --help
```

---

## 6. Local cloud sibling (optional)

If you have `omem-cloud` checked out next to `omem-oss`:

```
workspace/
├── omem-oss/
└── omem-cloud/
```

```bash
cd omem-cloud
make setup    # editable sibling + deps
make up       # API + Postgres → :8080
make doctor
```

Then follow [omem-cloud MCP setup](../../../omem-cloud/docs/guides/MCP_SETUP.md).

---

## 7. Contribute

Full guide: [CONTRIBUTING.md](../../CONTRIBUTING.md).

```bash
pip install -e ".[dev]"
pytest tests/ -q
```

- PRs target **`dev`**
- Rust is **not** required for most work (only `rust/` / SIMD)
- Releases: [RELEASING.md](./RELEASING.md) · versioning: [VERSIONING.md](./VERSIONING.md)

Architecture maps: [ARCHITECTURE.md](../architecture/ARCHITECTURE.md), [PROJECT_STRUCTURE.md](../architecture/PROJECT_STRUCTURE.md).

---

## 8. FAQ

**Does memory dump the whole DB into every prompt?**  
No. Agents call `recall` / `build_context` for a small top‑k or token-budgeted pack.

**`command not found: omem` in Cursor**  
Use the absolute path to the binary (`which omem` or `.venv/bin/omem`). Prefer `bash scripts/install_personal_mcp.sh`.

**Two tools see different memories**  
Mismatch on `--namespace` or `--db-path`. Call `mcp_status` in both and compare.

**Editable install breaks with `ModuleNotFoundError`**  
Reinstall from the checkout: `pip install -e ".[mcp,dev]"` and point MCP at `.venv/bin/omem`, not a stale global `omem`.
