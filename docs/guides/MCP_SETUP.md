# OMem - Claude Desktop & MCP Setup

This guide covers connecting OMem to **Claude Code**, **OpenCode**, Claude Desktop, Cursor IDE, or any MCP-compatible client so your AI gets persistent memory across every session.

**Personal multi-tool (Claude Code ↔ OpenCode):** see the short production guide → [`PERSONAL_MCP.md`](./PERSONAL_MCP.md)

---

## Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| Python | 3.10+ | MCP requires Python 3.10+ |
| pip | latest | `pip install --upgrade pip` |
| Claude Code / OpenCode / Cursor / Claude Desktop | latest | Any MCP client |

---

## Installation

```bash
pip install "omem-os[mcp]"
```

Verify it installed correctly:

```bash
omem health
```

Then:

```bash
python3 -c "from omem.integrations.mcp_server import _HAS_MCP; print('mcp', _HAS_MCP)"
```

---

## Personal production (recommended)

Pin a **shared namespace + DB** so every client sees the same memories:

```bash
omem serve --namespace personal --db-path ~/.omem/brain.db
```

Ready-made configs:

| Client | File |
|--------|------|
| Claude Code | [`deploy/mcp/claude_code.mcp.json`](../../deploy/mcp/claude_code.mcp.json) |
| OpenCode | [`deploy/mcp/opencode.mcp.json`](../../deploy/mcp/opencode.mcp.json) |
| Cursor | [`deploy/mcp/cursor.mcp.json`](../../deploy/mcp/cursor.mcp.json) |

Smoke test (no GUI required):

```bash
python3 scripts/mcp_personal_smoke.py
```

---

## Claude Desktop Setup

### 1. Find your config file

| OS | Path |
|---|---|
| macOS | `~/Library/Application Support/Claude/claude_desktop_config.json` |
| Windows | `%APPDATA%\Claude\claude_desktop_config.json` |

### 2. Add OMem to the config

```json
{
  "mcpServers": {
    "omem": {
      "command": "omem",
      "args": [
        "serve",
        "--namespace", "personal",
        "--db-path", "~/.omem/brain.db"
      ]
    }
  }
}
```

### 3. Restart Claude Desktop

Quit completely and reopen. You should see **OMem** listed in the MCP tools panel.

---

## Cursor IDE Setup

```json
{
  "mcpServers": {
    "omem": {
      "command": "omem",
      "args": [
        "serve",
        "--namespace", "personal",
        "--db-path", "~/.omem/brain.db"
      ]
    }
  }
}
```

---

## MCP Tools Reference

| Tool | Description |
|---|---|
| `mcp_status` | Confirm shared namespace + db path (use first) |
| `remember` | Store a fact, decision, preference, or observation |
| `recall` | Semantic search with optional type and time filters |
| `remember_decision` / `recall_decisions` | Architectural decision records |
| `remember_pr_context` / `recall_pr_context` | PR history |
| `remember_bug_fix` / `recall_bugs` | Root cause + fix |
| `reflect` | Generate high-level insights from recent episodic memories |
| `maintain` | Run the full sleep cycle: compress, forget, deduplicate |
| `resolve_conflict` | Detect and resolve contradicting memories |
| `remember_action` / `recall_action` | Procedural tool/action memories |
| `query_codebase` / `sync_codebase` / `ingest_codebase` | Code index tools |

---

## First Session Walkthrough

1. Open Claude Code. Ask: `Call mcp_status, then remember that my preferred language is Python.`
2. Open OpenCode (same machine, same MCP args). Ask: `Recall my preferred language.`
3. You should get the fact written from Claude Code.

---

## Namespace rules

1. `OMEM_NAMESPACE` / `--namespace` (best for multi-tool sharing)
2. Else git root basename under `OMEM_PROJECT_ROOT` or cwd
3. Else cwd basename

---

## Troubleshooting

**`command not found: omem`** — use the absolute path to the `omem` binary in MCP JSON.

**`No module named 'mcp'`** — `pip install "omem-os[mcp]"` (Python 3.10+).

**Different memories in two tools** — both must use identical `--namespace` and `--db-path`. Compare `mcp_status`.

**Permission error** — `mkdir -p ~/.omem && chmod 700 ~/.omem`
