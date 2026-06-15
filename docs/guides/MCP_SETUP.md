# OMem - Claude Desktop & MCP Setup

This guide covers connecting OMem to Claude Desktop, Cursor IDE, or any MCP-compatible client so your AI gets persistent memory across every session.

---

## Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| Python | 3.10+ | MCP requires Python 3.10+ |
| pip | latest | `pip install --upgrade pip` |
| Claude Desktop | latest | [Download](https://claude.ai/download) |
| — or Cursor IDE | latest | [Download](https://cursor.sh) |

---

## Installation

```bash
pip install "omem-os[mcp]"
```

Verify it installed correctly:

```bash
omem health
```

Expected output:

```
OMem health check passed.
  backend : sqlite
  db_path : /Users/<you>/.omem/brain.db
  memories: 0
  mcp     : available
```

---

## Claude Desktop Setup

### 1. Find your config file

| OS | Path |
|---|---|
| macOS | `~/Library/Application Support/Claude/claude_desktop_config.json` |
| Windows | `%APPDATA%\Claude\claude_desktop_config.json` |

### 2. Add OMem to the config

Open (or create) the file and add the `omem` block inside `"mcpServers"`:

```json
{
  "mcpServers": {
    "omem": {
      "command": "omem",
      "args": ["serve"]
    }
  }
}
```

If you already have other MCP servers listed, just add the `"omem"` key alongside them.

### 3. Restart Claude Desktop

Quit completely and reopen. You should see **OMem** listed in the MCP tools panel.

---

## Cursor IDE Setup

Open Cursor settings (`Cmd+,` on macOS) → search **MCP** → open `settings.json` manually.

Add the following inside your JSON config:

```json
{
  "mcpServers": {
    "omem": {
      "command": "omem",
      "args": ["serve"]
    }
  }
}
```

Cursor auto-detects the server on next launch.

---

## MCP Tools Reference

When OMem is connected, your AI client gains access to these tools:

| Tool | Description |
|---|---|
| `remember` | Store a fact, decision, preference, or observation |
| `recall` | Semantic search with optional type and time filters |
| `reflect` | Generate high-level insights from recent episodic memories |
| `maintain` | Run the full sleep cycle: compress, forget, deduplicate |
| `resolve_conflict` | Detect and resolve contradicting memories |
| `remember_action` | Store a tool call or agent action as a procedural memory |
| `recall_action` | Retrieve past actions relevant to the current task |
| `query_codebase` | Search indexed codebase memories by natural language |
| `sync_codebase` | Incrementally index changed files since last sync |
| `ingest_codebase` | Full initial index of a project directory |

---

## MCP Resources Reference

OMem exposes these read-only resources your client can subscribe to:

| Resource URI | Description |
|---|---|
| `omem://recent` | The 20 most recently added memories |
| `omem://top_insights` | Top REFLECTION-type memories by importance |
| `omem://status` | Live stats: memory count, graph edges, namespaces |
| `omem://graph` | Knowledge graph entity list |

---

## First Session Walkthrough

After connecting, test that OMem is working:

1. Open a new Claude Desktop conversation.
2. Type: `"Use OMem to remember that my preferred language is Python and I use dark mode."`
3. Claude should call the `remember` tool and confirm it stored both facts.
4. Close the conversation. Open a new one.
5. Type: `"What are my preferences?"`
6. Claude should call `recall` and return the stored facts.

That cross-session recall — from a completely new conversation — confirms OMem is working.

---

## Namespace Auto-Detection

When you run `omem serve` from inside a project directory that contains a `.git` folder, OMem automatically detects the project root and uses the folder name as the memory namespace.

This means:
- Memories stored during work on `~/projects/my-api` go into namespace `my-api`
- Switching to `~/projects/blog` gives Claude a clean, isolated memory space
- You can always override: `omem serve --namespace my-custom-ns`

---

## Troubleshooting

**`command not found: omem`**

The `omem` script was installed into a location not on your PATH. Find it with:

```bash
python -m site --user-base
# then look in <user-base>/bin/omem
```

Add that directory to your PATH, or use the full path in the config:

```json
{
  "mcpServers": {
    "omem": {
      "command": "/full/path/to/omem",
      "args": ["serve"]
    }
  }
}
```

---

**`ModuleNotFoundError: No module named 'mcp'`**

Install the MCP extra:

```bash
pip install "omem-os[mcp]"
```

Note: the `mcp` package requires Python 3.10+. Check your version:

```bash
python --version
```

---

**Permission error writing to `~/.omem/brain.db`**

```bash
mkdir -p ~/.omem
chmod 700 ~/.omem
```

---

**Claude does not call OMem tools**

- Confirm the server appears in Claude Desktop's settings under MCP.
- Run `omem health` in your terminal to confirm the binary works.
- Check Claude Desktop logs: `~/Library/Logs/Claude/` (macOS).

---

## Advanced: Custom DB Path

To store memories in a project-local directory instead of `~/.omem/brain.db`:

```json
{
  "mcpServers": {
    "omem": {
      "command": "omem",
      "args": ["serve", "--db-path", "/path/to/project/.omem/brain.db"]
    }
  }
}
```

This is useful for keeping project-specific memory isolated at the filesystem level.
