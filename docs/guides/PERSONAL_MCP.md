# Personal production MCP — Claude Code + OpenCode (+ Cursor)

Shared durable memory across coding agents on **one machine**, without a cloud account.

For the full client matrix and troubleshooting, see [MCP_SETUP.md](./MCP_SETUP.md).  
For team / remote memory, use [omem-cloud MCP](../../../omem-cloud/docs/guides/MCP_SETUP.md).

## Install (once)

```bash
cd omem-oss
python3 -m venv .venv
.venv/bin/pip install -U -e ".[mcp]"
# optional: stronger semantic recall
.venv/bin/pip install -U -e ".[mcp,embeddings]"
mkdir -p ~/.omem && chmod 700 ~/.omem
```

Generate client configs with the **absolute** `omem` path (avoids PATH / monorepo shadowing):

```bash
bash scripts/install_personal_mcp.sh
```

That writes `artifacts/personal-mcp/*.mcp.json` and updates `~/.cursor/mcp.json` when present.

## One rule for seamless sharing

Both clients must use the **same**:

| Setting | Value |
|---------|--------|
| Namespace | `personal` (or any shared name) |
| DB path | absolute path to `~/.omem/brain.db` |

```bash
omem serve --namespace personal --db-path "$HOME/.omem/brain.db"
```

## Claude Code

Copy [`deploy/mcp/claude_code.mcp.json`](../../deploy/mcp/claude_code.mcp.json) (or the generated artifact) into Claude Code’s MCP settings. Prefer the artifact from `install_personal_mcp.sh` — it already has absolute paths.

Restart Claude Code, then ask:

> Call `mcp_status` on OMem. Then remember that I prefer Claude Code and OpenCode with shared OMem memory.

## OpenCode

Same block as Claude Code → OpenCode MCP config. Restart OpenCode.

Ask:

> Call `mcp_status`, then recall what I prefer for coding agents.

You should see the same namespace/db and the memory written from Claude Code.

## Cursor (optional)

```bash
omem init --cursor
# or: bash scripts/install_personal_mcp.sh
```

## Absolute-path template

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

Expand `~` yourself — many clients do not.

## Verify

```bash
python3 scripts/mcp_personal_smoke.py
```

Expect `✔ PASS — shared MCP memory works`.

In each client, call **`mcp_status`** — `namespace` and `db_path` must match.

## Daily habit (makes it seamless)

| When | Do |
|------|-----|
| Starting a task | `recall` / `recall_decisions` / `recall_bugs` |
| Making a choice | `remember_decision` |
| Fixing a bug | `remember_bug_fix` |
| Ending a session | `remember` what’s done + what’s next |

Optional system nudge: MCP prompt `omem/coding_agent`.

## What this is / isn’t

| Is | Isn’t |
|----|--------|
| Durable shared memory across MCP clients | Automatic full chat-transcript sync |
| Local-first (SQLite on your machine) | Multi-laptop team SaaS (that’s omem-cloud) |
| Works while staying on Claude Code | A reason to switch IDEs |

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| Different namespaces in `mcp_status` | Pin `--namespace personal` in **both** configs |
| Tools missing | `pip install "omem-os[mcp]"` · Python 3.10+ · restart client |
| `command not found: omem` | Absolute path to `.venv/bin/omem` |
| Recall empty | Same absolute `--db-path` · confirm with `remember` then `recall` |
| `ImportError` / shadowed `omem` | Use absolute `.venv/bin/omem` · re-run `scripts/install_personal_mcp.sh` |
| Weak semantic recall | `pip install 'omem-os[embeddings]'` |

Full tool list: [MCP_SETUP.md](./MCP_SETUP.md).
