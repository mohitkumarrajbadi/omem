# MCP setup — local OMem (Cursor, Claude, OpenCode)

Connect any MCP client to **local** OMem so agents share durable memory on your machine.

| You want | Guide |
|----------|--------|
| **Local SQLite** (this page) | Solo / laptop — `omem serve` |
| Shared Claude Code ↔ OpenCode | [PERSONAL_MCP.md](./PERSONAL_MCP.md) |
| **Team cloud** (Postgres + API key) | [omem-cloud MCP_SETUP](../../../omem-cloud/docs/guides/MCP_SETUP.md) |

---

## 60-second path (Cursor)

```bash
# Mac / Linux (recommended — avoids system-pip errors)
curl -fsSL https://raw.githubusercontent.com/mohitkumarrajbadi/omem/main/scripts/install.sh | bash -s -- --cursor

# or: uv tool install 'omem-os[mcp]' && omem init --cursor
```

Windows: see [INSTALL.md](./INSTALL.md).

1. **Restart Cursor** completely.
2. Open the MCP panel — you should see tools under `omem`.
3. Ask:

> Call `mcp_status`, then `remember` "MCP connected", then `recall` "MCP connected".

`omem init --cursor` expands the DB path and merges into `~/.cursor/mcp.json` without wiping other servers.

---

## Prerequisites

| Requirement | Notes |
|-------------|--------|
| Python **3.10+** | MCP extra needs 3.10+ |
| `pip install "omem-os[mcp]"` | Installs the `omem` CLI + MCP server |
| Absolute paths in MCP JSON | Many clients **do not expand `~`** |

Verify:

```bash
omem health
omem --version
python3 -c "from omem.integrations.mcp_server import _HAS_MCP; print('mcp', _HAS_MCP)"
```

Expect `mcp True`. If `False`, reinstall with Python 3.10+: `pip install "omem-os[mcp]"`.

---

## The one rule for shared memory

Every client must use the **same**:

| Setting | Example |
|---------|---------|
| Namespace | `personal` |
| DB path | `/Users/YOU/.omem/brain.db` (absolute) |

```bash
omem serve --namespace personal --db-path "$HOME/.omem/brain.db"
```

Put those **same** args in every client's MCP config.

---

## Install helpers

### From PyPI + Cursor only

```bash
omem init --cursor
```

### From a checkout (Claude Code + OpenCode + Cursor)

```bash
cd omem-oss
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[mcp]"
bash scripts/install_personal_mcp.sh   # writes absolute-path configs
python3 scripts/mcp_personal_smoke.py  # expect ✔ PASS
```

Generated files: `artifacts/personal-mcp/*.mcp.json`  
Cursor home updated when `~/.cursor` exists.

Ready-made templates (replace `omem` + expand `~` yourself): [`deploy/mcp/`](../../deploy/mcp/).

---

## Client configs

Replace `/FULL/PATH/TO/omem` with `$(which omem)` or `.venv/bin/omem`, and expand the DB path.

### Cursor — `~/.cursor/mcp.json`

```json
{
  "mcpServers": {
    "omem": {
      "command": "/FULL/PATH/TO/omem",
      "args": [
        "serve",
        "--namespace", "personal",
        "--db-path", "/Users/YOU/.omem/brain.db",
        "--mode", "auto"
      ]
    }
  }
}
```

### Working mode (`manual` | `auto` | `all`)

MCP cannot force the model to call tools — **mode** tells the agent how aggressive to be:

| Mode | Behavior |
|------|----------|
| `manual` | Remember / snapshot **only when you ask** |
| `auto` (default) | Proactively remember decisions, prefs, fixes; snapshot before risk |
| `all` | Aggressive remember + frequent snapshots |

Set via:

```bash
omem serve --mode auto
# or in chat:
# Call working_mode with mode="auto"
# or Console → MCP → Working mode → Save / Write mcp.json
```

Persists to `~/.omem/mcp_mode`. Restart the MCP client after changing.

### Claude Desktop — macOS

`~/Library/Application Support/Claude/claude_desktop_config.json`

```json
{
  "mcpServers": {
    "omem": {
      "command": "/FULL/PATH/TO/omem",
      "args": [
        "serve",
        "--namespace", "personal",
        "--db-path", "/Users/YOU/.omem/brain.db",
        "--mode", "auto"
      ]
    }
  }
}
```

Quit Claude Desktop fully, then reopen.

### Claude Code

Project or user MCP settings (`.mcp.json` / MCP UI) — same `mcpServers.omem` block as Cursor.

### OpenCode — `~/.config/opencode/opencode.jsonc`

```jsonc
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "omem": {
      "type": "local",
      "enabled": true,
      "command": [
        "/FULL/PATH/TO/omem",
        "serve",
        "--namespace", "personal",
        "--db-path", "/Users/YOU/.omem/brain.db"
      ]
    }
  }
}
```

Check: `opencode mcp list`

---

## First session walkthrough

1. **Cursor / Claude Code:**  
   `Call mcp_status, then remember that my preferred language is Python.`
2. **OpenCode** (same machine, same namespace + db-path):  
   `Call mcp_status, then recall my preferred language.`
3. You should see the fact written from the other client.  
   `mcp_status` must show matching `namespace` and `db_path`.

Daily habit: [PERSONAL_MCP.md](./PERSONAL_MCP.md#daily-habit-makes-it-seamless).

---

## MCP tools (default)

| Tool | What it does |
|------|----------------|
| `mcp_status` | Confirm namespace + db path + **mode** (**call first**) |
| `working_mode` | Get/set `manual` \| `auto` \| `all` |
| `snapshot` / `list_snapshots` / `rollback` | Session checkpoints |
| `lineage` | Demo story: which memory caused a decision |
| `remember` / `recall` | Store and search durable memory |
| `remember_decision` / `recall_decisions` | Architectural decisions |
| `remember_pr_context` / `recall_pr_context` | PR history |
| `remember_bug_fix` / `recall_bugs` | Root cause + fix |
| `remember_action` / `recall_action` | Procedural / tool recipes |
| `reflect` | Insights from recent episodic memories |
| `maintain` | Compress / forget / dedupe cycle |
| `resolve_conflict` | Contradicting memories |
| `get_codebase_summary` | Decisions + recent PR/bug context |

**Alpha (off by default):** `query_codebase`, `sync_codebase`, `ingest_codebase` — enable with `OMEM_ENABLE_EXPERIMENTAL_AST=1` in the MCP server env.

---

## Namespace rules

Resolution order when you do **not** pass `--namespace`:

1. `OMEM_NAMESPACE` env
2. Else git root basename under `OMEM_PROJECT_ROOT` or cwd
3. Else cwd basename

For multi-tool sharing, **always** pin `--namespace` (and `--db-path`) explicitly.

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `command not found: omem` | Set `"command"` to an absolute path (`which omem` or `.venv/bin/omem`) |
| `No module named 'mcp'` / `_HAS_MCP False` | `pip install "omem-os[mcp]"` on Python 3.10+ |
| Tools missing after config change | Fully quit and restart the client |
| Different memories in two apps | Same `--namespace` **and** absolute `--db-path`; compare `mcp_status` |
| Empty recall after remember | Confirm write with `mcp_status`; check you are not on cloud vs local |
| `~` in db-path ignored | Expand to `/Users/YOU/.omem/brain.db` |
| `ImportError` / shadowed `omem` | Prefer `.venv/bin/omem`; run `scripts/install_personal_mcp.sh` |
| Permission error on `~/.omem` | `mkdir -p ~/.omem && chmod 700 ~/.omem` |
| Weak semantic recall | `pip install "omem-os[embeddings]"` (lexical fallback still works) |

Smoke test (no GUI):

```bash
python3 scripts/mcp_personal_smoke.py
```

---

## Related

- [Developer guide](./DEVELOPER.md) — install, API, CLI
- [Personal MCP](./PERSONAL_MCP.md) — Claude Code ↔ OpenCode production habit
- [Cloud MCP](../../../omem-cloud/docs/guides/MCP_SETUP.md) — remote `/mcp` + API keys
- [deploy/mcp/README.md](../../deploy/mcp/README.md) — template JSON files
