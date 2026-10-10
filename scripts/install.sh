#!/usr/bin/env bash
# OMem one-line installer for macOS / Linux.
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/mohitkumarrajbadi/omem/main/scripts/install.sh | bash
#   curl -fsSL ... | bash -s -- --cursor
#   curl -fsSL ... | bash -s -- --no-mcp
set -euo pipefail

OMEM_HOME="${OMEM_HOME:-$HOME/.omem}"
VENV="$OMEM_HOME/venv"
BIN_DIR="${OMEM_BIN_DIR:-$HOME/.local/bin}"
WITH_MCP=1
WITH_CURSOR=0
PURE_PYTHON=1

for arg in "$@"; do
  case "$arg" in
    --cursor) WITH_CURSOR=1 ;;
    --no-mcp) WITH_MCP=0 ;;
    --rust) PURE_PYTHON=0 ;;
    -h|--help)
      cat <<EOF
Install OMem (omem-os) into ~/.omem/venv and put \`omem\` on PATH.

  --cursor   Also write ~/.cursor/mcp.json (omem init --cursor)
  --no-mcp   Skip MCP extra (smaller install)
  --rust     Allow compiling the optional Rust extension from source
EOF
      exit 0
      ;;
  esac
done

say() { printf '%s\n' "$*"; }
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

pick_python() {
  local cand
  for cand in python3.13 python3.12 python3.11 python3.10 python3; do
    if command -v "$cand" >/dev/null 2>&1; then
      if "$cand" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)'; then
        echo "$cand"
        return 0
      fi
    fi
  done
  return 1
}

say "═══ OMem installer ═══"
say "Install dir: $OMEM_HOME"

mkdir -p "$OMEM_HOME" "$BIN_DIR"
chmod 700 "$OMEM_HOME" 2>/dev/null || true

PY="$(pick_python)" || die "Need Python 3.10+ (3.11–3.13 recommended for prebuilt wheels).
Install from https://www.python.org/downloads/ or: brew install python@3.12"
say "Using $($PY -V) at $(command -v "$PY")"

if [[ ! -x "$VENV/bin/python" ]]; then
  "$PY" -m venv "$VENV"
fi

EXTRA=""
[[ "$WITH_MCP" == "1" ]] && EXTRA="[mcp]"
export OMEM_PURE_PYTHON="${OMEM_PURE_PYTHON:-$PURE_PYTHON}"

say "Installing omem-os${EXTRA} into $VENV …"
if command -v uv >/dev/null 2>&1; then
  # uv into our venv — fast, still isolated (not uv tool / global PATH games)
  OMEM_PURE_PYTHON="$OMEM_PURE_PYTHON" uv pip install --python "$VENV/bin/python" -U "omem-os${EXTRA}"
else
  "$VENV/bin/python" -m pip install -U pip setuptools wheel >/dev/null
  if ! OMEM_PURE_PYTHON="$OMEM_PURE_PYTHON" "$VENV/bin/pip" install -U "omem-os${EXTRA}"; then
    die "pip install failed. Try: brew install python@3.12 && re-run this script
Or install uv (https://docs.astral.sh/uv/) and re-run.
Report: https://github.com/mohitkumarrajbadi/omem/issues"
  fi
fi

ln -sfn "$VENV/bin/omem" "$BIN_DIR/omem"
OMEM_BIN="$BIN_DIR/omem"
[[ -x "$OMEM_BIN" ]] || die "omem binary missing at $OMEM_BIN"

ENV_FILE="$OMEM_HOME/env"
if [[ ! -f "$ENV_FILE" ]]; then
  cat >"$ENV_FILE" <<EOF
export OMEM_DB_PATH="$OMEM_HOME/brain.db"
export OMEM_NAMESPACE=personal
export OMEM_MCP_MODE=auto
export OMEM_EMBEDDER=hash
EOF
fi

export OMEM_DB_PATH="${OMEM_DB_PATH:-$OMEM_HOME/brain.db}"
export OMEM_NAMESPACE="${OMEM_NAMESPACE:-personal}"
export OMEM_MCP_MODE="${OMEM_MCP_MODE:-auto}"
export OMEM_EMBEDDER="${OMEM_EMBEDDER:-hash}"

VER="$("$OMEM_BIN" --version 2>/dev/null || true)"
say "Installed: $OMEM_BIN  ($VER)"

if [[ "$WITH_CURSOR" == "1" ]]; then
  say "Writing Cursor MCP config…"
  "$OMEM_BIN" init --cursor --db-path "$OMEM_DB_PATH" || true
fi

case ":$PATH:" in
  *":$BIN_DIR:"*) ;;
  *)
    say ""
    say "Add to PATH (zsh/bash):"
    say "  export PATH=\"$BIN_DIR:\$PATH\""
    PROFILE=""
    if [[ -n "${ZSH_VERSION:-}" ]] || [[ "${SHELL:-}" == *zsh* ]]; then
      PROFILE="$HOME/.zshrc"
    elif [[ "${SHELL:-}" == *bash* ]]; then
      PROFILE="$HOME/.bashrc"
    fi
    if [[ -n "$PROFILE" ]] && [[ -f "$PROFILE" ]] && ! grep -qF "$BIN_DIR" "$PROFILE" 2>/dev/null; then
      {
        echo ""
        echo "# OMem CLI"
        echo "export PATH=\"$BIN_DIR:\$PATH\""
      } >>"$PROFILE"
      say "Appended PATH to $PROFILE"
    fi
    ;;
esac

say ""
say "✔ Done. Next:"
say "  omem health"
say "  omem init --cursor"
say "  omem console"
say ""
say "If 'omem' is not found, open a new terminal or:"
say "  export PATH=\"$BIN_DIR:\$PATH\""
