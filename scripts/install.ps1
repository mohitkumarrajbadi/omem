# OMem one-line installer for Windows (PowerShell).
# Usage:
#   irm https://raw.githubusercontent.com/mohitkumarrajbadi/omem/main/scripts/install.ps1 | iex
param(
    [switch]$Cursor,
    [switch]$NoMcp,
    [switch]$Rust
)

$ErrorActionPreference = "Stop"
$OmemHome = if ($env:OMEM_HOME) { $env:OMEM_HOME } else { Join-Path $HOME ".omem" }
$Venv = Join-Path $OmemHome "venv"
$BinDir = if ($env:OMEM_BIN_DIR) { $env:OMEM_BIN_DIR } else { Join-Path $HOME ".local\bin" }

Write-Host "=== OMem installer (Windows) ==="
Write-Host "Install dir: $OmemHome"

New-Item -ItemType Directory -Force -Path $OmemHome | Out-Null
New-Item -ItemType Directory -Force -Path $BinDir | Out-Null

function Find-Python {
    foreach ($name in @("python3.13", "python3.12", "python3.11", "python3.10", "python", "py")) {
        $cmd = Get-Command $name -ErrorAction SilentlyContinue
        if (-not $cmd) { continue }
        if ($name -eq "py") {
            try {
                & py -3.12 -c "import sys; raise SystemExit(0 if sys.version_info >= (3,10) else 1)" 2>$null
                if ($LASTEXITCODE -eq 0) { return @("py", "-3.12") }
                & py -3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3,10) else 1)" 2>$null
                if ($LASTEXITCODE -eq 0) { return @("py", "-3") }
            } catch { }
            continue
        }
        try {
            & $cmd.Source -c "import sys; raise SystemExit(0 if sys.version_info >= (3,10) else 1)" 2>$null
            if ($LASTEXITCODE -eq 0) { return @($cmd.Source) }
        } catch { }
    }
    return $null
}

$py = Find-Python
if (-not $py) {
    throw "Need Python 3.10+ (3.11-3.13 recommended). Install from https://www.python.org/downloads/ and re-run."
}
Write-Host ("Using Python: " + ($py -join " "))

$pyExe = $py[0]
$pyArgs = @()
if ($py.Length -gt 1) { $pyArgs = $py[1..($py.Length - 1)] }

if (-not (Test-Path (Join-Path $Venv "Scripts\python.exe"))) {
    & $pyExe @pyArgs -m venv $Venv
}

$python = Join-Path $Venv "Scripts\python.exe"
$pip = Join-Path $Venv "Scripts\pip.exe"
$env:OMEM_PURE_PYTHON = if ($Rust) { "0" } else { "1" }
$spec = if ($NoMcp) { "omem-os" } else { "omem-os[mcp]" }

Write-Host "Installing $spec into $Venv ..."
$uv = Get-Command uv -ErrorAction SilentlyContinue
if ($uv) {
    & uv pip install --python $python -U $spec
} else {
    & $python -m pip install -U pip setuptools wheel | Out-Null
    & $pip install -U $spec
    if ($LASTEXITCODE -ne 0) { throw "pip install failed" }
}

$omemSrc = Join-Path $Venv "Scripts\omem.exe"
$omemDst = Join-Path $BinDir "omem.exe"
Copy-Item -Force $omemSrc $omemDst

$env:OMEM_DB_PATH = if ($env:OMEM_DB_PATH) { $env:OMEM_DB_PATH } else { Join-Path $OmemHome "brain.db" }
$env:OMEM_NAMESPACE = if ($env:OMEM_NAMESPACE) { $env:OMEM_NAMESPACE } else { "personal" }
$env:OMEM_MCP_MODE = if ($env:OMEM_MCP_MODE) { $env:OMEM_MCP_MODE } else { "auto" }
$env:OMEM_EMBEDDER = if ($env:OMEM_EMBEDDER) { $env:OMEM_EMBEDDER } else { "hash" }

Write-Host "Installed: $omemDst"
& $omemDst --version

if ($Cursor) {
    Write-Host "Writing Cursor MCP config..."
    & $omemDst init --cursor --db-path $env:OMEM_DB_PATH
}

$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
if ($userPath -notlike "*$BinDir*") {
    [Environment]::SetEnvironmentVariable("Path", "$BinDir;$userPath", "User")
    $env:Path = "$BinDir;$env:Path"
    Write-Host "Added $BinDir to your user PATH (new terminals pick this up)."
}

Write-Host ""
Write-Host "Done. Next:"
Write-Host "  omem health"
Write-Host "  omem init --cursor"
Write-Host "  omem console"
