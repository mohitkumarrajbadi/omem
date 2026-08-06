# Personal production MCP — Claude Code + OpenCode (+ Cursor)

Give this to a manager who wants **shared durable memory** across coding agents
**without** switching vendors (stay on Claude Code; use OpenCode in parallel).

## Install (once)

```bash
cd omem-oss
python3 -m venv .venv
.venv/bin/pip install -U -e ".[mcp]"
# optional: stronger semantic recall
.venv/bin/pip install -U -e ".[mcp,embeddings]"
mkdir -p ~/.omem && chmod 700 ~/.omem
```

Generate client configs with the **absolute** `omem` path (required when `omem` on PATH is broken or when a monorepo `omem` symlink shadows the package):

```bash
bash scripts/install_personal_mcp.sh
```

That writes `artifacts/personal-mcp/*.mcp.json` and updates `~/.cursor/mcp.json`.

If `omem` is not on PATH, use the absolute path as `"command"` (the install script does this for you).

## One rule for seamless sharing

Both clients must use the **same**:

| Setting | Value |
|---------|--------|
| Namespace | `personal` (or any shared name) |
| DB path | `~/.omem/brain.db` |

```bash
omem serve --namespace personal --db-path ~/.omem/brain.db
```

## Claude Code

Copy [`deploy/mcp/claude_code.mcp.json`](../../deploy/mcp/claude_code.mcp.json) into Claude Code’s MCP settings
(or merge the `omem` block). Restart Claude Code.

Then ask:

> Call `mcp_status` on OMem. Then remember that I prefer Claude Code and OpenCode with shared OMem memory.

## OpenCode

Copy [`deploy/mcp/opencode.mcp.json`](../../deploy/mcp/opencode.mcp.json) into OpenCode’s MCP config
(same args as Claude Code). Restart OpenCode.

Ask:

> Call `mcp_status`, then recall what I prefer for coding agents.

You should see the same namespace/db and the memory written from Claude Code.

## Cursor (optional)

Same block: [`deploy/mcp/cursor.mcp.json`](../../deploy/mcp/cursor.mcp.json) → `~/.cursor/mcp.json`.

## Absolute-path template (when `omem` is not on PATH)

```json
{
  "mcpServers": {
    "omem": {
      "command": "/FULL/PATH/TO/omem",
      "args": [
        "serve",
        "--namespace", "personal",
        "--db-path", "/Users/YOU/.omem/brain.db"
      ]
    }
  }
}
```

Expand `~` yourself if the client does not expand home directories.

## Verify

```bash
# From the omem-oss checkout (or after pip install -e .)
python3 scripts/mcp_personal_smoke.py
```

Expect `✔ PASS — shared MCP memory works`.

In each client, call the tool **`mcp_status`** — `namespace` and `db_path` must match.

## Daily habit (makes it “seamless”)

| When | Do |
|------|-----|
| Starting a task | `recall` / `recall_decisions` / `recall_bugs` |
| Making a choice | `remember_decision` |
| Fixing a bug | `remember_bug_fix` |
| Ending a session | `remember` what’s done + what’s next |

Optional system nudge: use the MCP prompt `omem/coding_agent`.

## What this is / isn’t

| Is | Isn’t |
|----|--------|
| Durable shared memory across MCP clients | Automatic full chat-transcript sync |
| Local-first (SQLite on your machine) | Multi-laptop team SaaS (that’s omem-cloud) |
| Works while staying on Claude Code | A reason to switch to Copilot |

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| Different namespaces in `mcp_status` | Pin `--namespace personal` in **both** configs |
| Tools missing | `pip install "omem-os[mcp]"` · Python 3.10+ |
| `command not found: omem` | Use absolute path to the `omem` binary |
| Recall empty | Same `--db-path` · confirm write with `remember` then `recall` |
| `ImportError: __version__` / shadowed `omem` | Use **absolute** `.venv/bin/omem` as `command` (not bare `omem` / `python -m`) · run `scripts/install_personal_mcp.sh` |
| Weak semantic recall | `pip install 'omem-os[embeddings]'` (lexical fallback still works) |

Full tool list: [`MCP_SETUP.md`](./MCP_SETUP.md)
