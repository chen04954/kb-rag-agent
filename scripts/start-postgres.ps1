# Start local PostgreSQL 17. Run from PowerShell for clear output.
$ErrorActionPreference = "Stop"
$PgRoot = "D:\PostgreSQL\pg17"
$PgBin = Join-Path $PgRoot "pgsql\bin"
$PgData = Join-Path $PgRoot "data"
$PgLog = Join-Path $PgRoot "log\postgresql.log"
$PgCtl = Join-Path $PgBin "pg_ctl.exe"

if (-not (Test-Path $PgCtl)) {
    throw "pg_ctl not found: $PgCtl"
}

$logDir = Split-Path $PgLog -Parent
if (-not (Test-Path $logDir)) {
    New-Item -ItemType Directory -Path $logDir | Out-Null
}

& $PgCtl -D $PgData status 2>$null
if ($LASTEXITCODE -eq 0) {
    Write-Host "PostgreSQL already running."
    & $PgCtl -D $PgData status
    exit 0
}

Write-Host "Starting PostgreSQL..."
& $PgCtl -D $PgData -l $PgLog start
if ($LASTEXITCODE -ne 0) {
    throw "Start failed. See log: $PgLog"
}

& $PgCtl -D $PgData status
Write-Host "Log file: $PgLog"
