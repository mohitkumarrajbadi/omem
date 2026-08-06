#!/usr/bin/env bash
# Wire personal production OMem MCP for Claude Code / OpenCode / Cursor.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OMEM_BIN="${OMEM_BIN:-}"
DB_PATH="${OMEM_DB_PATH:-$HOME/.omem/brain.db}"
NAMESPACE="${OMEM_NAMESPACE:-personal}"

if [[ -z "$OMEM_BIN" ]]; then
  if [[ -x "$ROOT/.venv/bin/omem" ]]; then
    OMEM_BIN="$ROOT/.venv/bin/omem"
  elif command -v omem >/dev/null 2>&1; then
    OMEM_BIN="$(command -v omem)"
  else
    echo "omem not found. Install first:"
    echo "  cd \"$ROOT\" && python3 -m venv .venv && .venv/bin/pip install -e '.[mcp]'"
    exit 1
  fi
fi

# Verify the binary can import the real package (not a shadowed namespace).
if ! "$OMEM_BIN" --version >/dev/null 2>&1; then
  echo "Broken omem at: $OMEM_BIN"
  echo "Prefer the venv binary: $ROOT/.venv/bin/omem"
  exit 1
fi

mkdir -p "$HOME/.omem"
chmod 700 "$HOME/.omem" 2>/dev/null || true

block="$(cat <<EOF
{
  "mcpServers": {
    "omem": {
      "command": "$OMEM_BIN",
      "args": [
        "serve",
        "--namespace", "$NAMESPACE",
        "--db-path", "$DB_PATH"
      ]
    }
  }
}
EOF
)"

out_dir="$ROOT/artifacts/personal-mcp"
mkdir -p "$out_dir"
echo "$block" > "$out_dir/claude_code.mcp.json"
echo "$block" > "$out_dir/opencode.mcp.json"
echo "$block" > "$out_dir/cursor.mcp.json"

# Install Cursor config when present
if [[ -d "$HOME/.cursor" ]]; then
  cp "$out_dir/cursor.mcp.json" "$HOME/.cursor/mcp.json"
  echo "Updated ~/.cursor/mcp.json"
fi

cat <<EOF

✔ Personal MCP configs written to:
  $out_dir/

Use the SAME command + namespace + db-path in every client:
  command:   $OMEM_BIN
  namespace: $NAMESPACE
  db_path:   $DB_PATH

Verify:
  cd \"$ROOT\" && python scripts/mcp_personal_smoke.py

Then restart Claude Code / OpenCode / Cursor and call tool: mcp_status

EOF
