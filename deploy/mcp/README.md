# MCP client configs (local / personal)

These are **templates**. Prefer generating absolute-path configs:

```bash
# from omem-oss checkout
pip install -e ".[mcp]"
bash scripts/install_personal_mcp.sh
# → artifacts/personal-mcp/*.mcp.json
```

Or for Cursor only: `omem init --cursor`

| File | Client |
|------|--------|
| `claude_code.mcp.json` | Claude Code |
| `opencode.mcp.json` | OpenCode |
| `cursor.mcp.json` | Cursor (`~/.cursor/mcp.json`) |

**Critical**

1. Keep `--namespace` and `--db-path` identical in every client.
2. Replace `"command": "omem"` with an **absolute** path (`which omem` or `.venv/bin/omem`).
3. Expand `~` in `--db-path` — many MCP hosts do not expand home.

Guide: [`docs/guides/MCP_SETUP.md`](../../docs/guides/MCP_SETUP.md) · short personal guide: [`docs/guides/PERSONAL_MCP.md`](../../docs/guides/PERSONAL_MCP.md)

```bash
pip install "omem-os[mcp]"
# optional better semantic recall:
pip install "omem-os[mcp,embeddings]"
python3 scripts/mcp_personal_smoke.py
```

**Cloud / remote MCP** (different product path): [`omem-cloud/docs/guides/MCP_SETUP.md`](../../../omem-cloud/docs/guides/MCP_SETUP.md)
