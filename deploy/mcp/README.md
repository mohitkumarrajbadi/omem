# MCP client configs (personal production)

Copy the matching JSON into your client, or merge the `"omem"` block.

| File | Client |
|------|--------|
| `claude_code.mcp.json` | Claude Code |
| `opencode.mcp.json` | OpenCode |
| `cursor.mcp.json` | Cursor |

**Critical:** keep `--namespace` and `--db-path` identical in every client.

Guide: [`docs/guides/PERSONAL_MCP.md`](../docs/guides/PERSONAL_MCP.md)

```bash
pip install "omem-os[mcp]"
# optional better semantic recall:
pip install "omem-os[mcp,embeddings]"
python3 scripts/mcp_personal_smoke.py
```
