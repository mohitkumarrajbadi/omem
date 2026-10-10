# Install OMem (Mac · Windows · Linux)

Super-simple path first. Use raw `pip` only inside a venv.

## One-liner (recommended)

### macOS / Linux

```bash
curl -fsSL https://raw.githubusercontent.com/mohitkumarrajbadi/omem/main/scripts/install.sh | bash
```

Wire Cursor in the same step:

```bash
curl -fsSL https://raw.githubusercontent.com/mohitkumarrajbadi/omem/main/scripts/install.sh | bash -s -- --cursor
```

### Windows (PowerShell)

```powershell
irm https://raw.githubusercontent.com/mohitkumarrajbadi/omem/main/scripts/install.ps1 | iex
```

With Cursor MCP:

```powershell
& ([scriptblock]::Create((irm https://raw.githubusercontent.com/mohitkumarrajbadi/omem/main/scripts/install.ps1))) -Cursor
```

### What the installer does

1. Creates `~/.omem/venv` (or uses `uv tool install` if `uv` is available)
2. Installs `omem-os[mcp]` with **`OMEM_PURE_PYTHON=1`** (avoids Rust compile failures)
3. Puts `omem` on `~/.local/bin` (and PATH)
4. Defaults: `OMEM_NAMESPACE=personal`, `OMEM_MCP_MODE=auto`, `OMEM_EMBEDDER=hash`

Then:

```bash
omem health
omem init --cursor
omem console
```

## uv (great alternative)

```bash
uv tool install 'omem-os[mcp]'
omem init --cursor
```

## pip (only in a venv)

```bash
python3.12 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
OMEM_PURE_PYTHON=1 pip install -U pip 'omem-os[mcp]'
omem init --cursor
```

Do **not** `pip install` into Homebrew/system Python — you will hit `externally-managed-environment`.

## Python versions

| Version | Notes |
|---------|--------|
| **3.11–3.13** | Best — prebuilt wheels on PyPI |
| 3.10 | Works (MCP requires ≥3.10) |
| 3.14 | May build from sdist; use installer + `OMEM_PURE_PYTHON=1` |
| ≤3.9 | Not supported for MCP |

## Why bare pip fails

| Error | Fix |
|-------|-----|
| `externally-managed-environment` | Use the curl installer or a venv / `uv` |
| Rust / `maturin` / `cargo` / PyO3 build error | `OMEM_PURE_PYTHON=1 pip install omem-os` (or the installer) |
| `No module named 'mcp'` | Python ≥3.10 and `omem-os[mcp]` |
| `omem: command not found` | Open a new terminal; ensure `~/.local/bin` is on PATH |
| Wrong package | Package name is **`omem-os`**, CLI is **`omem`** |

## Verify

```bash
omem --version
omem health
python3 -c "from omem.integrations.mcp_server import _HAS_MCP; print('mcp', _HAS_MCP)"
```

Expect `mcp True` with the `[mcp]` extra on Python 3.10+.
