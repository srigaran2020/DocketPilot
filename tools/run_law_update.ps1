# Weekly law update, run by Windows Task Scheduler (see tools\schedule_law_update.ps1). Can also be run by hand:
#     .\tools\run_law_update.ps1
# Starts the databases if needed, fetches every Act again from India Code, records what changed, and writes a
# log to data\law_updates\update-<date>.log. Uses no AI.
$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$logDir = Join-Path $root "data\law_updates"
New-Item -ItemType Directory -Force $logDir | Out-Null
$log = Join-Path $logDir ("update-" + (Get-Date -Format "yyyy-MM-dd_HHmm") + ".log")
function Say($m) { $line = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $m"; Write-Host $line; Add-Content -Path $log -Value $line -Encoding UTF8 }

Say "DocketPilot weekly law update starting"

# 1. Docker Desktop must be running for the databases.
docker info *> $null
if ($LASTEXITCODE -ne 0) {
    $desktop = "$env:ProgramFiles\Docker\Docker\Docker Desktop.exe"
    if (Test-Path $desktop) { Say "Starting Docker Desktop..."; Start-Process $desktop }
    for ($i = 0; $i -lt 60; $i++) { Start-Sleep -Seconds 5; docker info *> $null; if ($LASTEXITCODE -eq 0) { break } }
    if ($LASTEXITCODE -ne 0) { Say "FAILED: Docker is not running, so the databases are unavailable. Will try next week."; exit 1 }
}

# 2. Database up and on the latest schema.
docker compose up -d postgres 2>&1 | Out-Null
for ($i = 0; $i -lt 30; $i++) {
    docker compose exec -T postgres pg_isready -U docketpilot -d docketpilot *> $null
    if ($LASTEXITCODE -eq 0) { break }
    Start-Sleep -Seconds 2
}
$py = Join-Path $root ".venv\Scripts\python.exe"
& $py -m alembic upgrade head 2>&1 | Out-Null

# 3. The update itself.
$env:OPENBLAS_NUM_THREADS = "1"
$env:PYTHONIOENCODING = "utf-8"
& $py -m docketpilot.ingestion.update_laws 2>&1 | ForEach-Object { $l = "$_"; Write-Host $l; Add-Content -Path $log -Value $l -Encoding UTF8 }
$code = $LASTEXITCODE
Say ("Finished with exit code " + $code)
exit $code
