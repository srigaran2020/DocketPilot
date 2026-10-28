# Start DocketPilot with one command:   .\start.ps1
# Databases run in Docker; the API and web app run from the project's Python environment.
# Then open http://127.0.0.1:8000   (stop with Ctrl+C; stop databases with: docker compose stop)
$ErrorActionPreference = "Stop"
$py = ".\.venv\Scripts\python.exe"

Write-Host "Starting databases (PostgreSQL, Qdrant, Redis, file storage)..." -ForegroundColor Cyan
docker compose up -d postgres qdrant redis objectstore
if ($LASTEXITCODE -ne 0) { Write-Host "Docker failed. Is Docker Desktop running?" -ForegroundColor Red; exit 1 }

Write-Host "Waiting for PostgreSQL..." -ForegroundColor Cyan
for ($i = 0; $i -lt 30; $i++) {
    docker compose exec -T postgres pg_isready -U docketpilot -d docketpilot *> $null
    if ($LASTEXITCODE -eq 0) { break }
    Start-Sleep -Seconds 2
}

Write-Host "Applying database migrations..." -ForegroundColor Cyan
& $py -m alembic upgrade head

$env:OPENBLAS_NUM_THREADS = "1"
Write-Host "`nDocketPilot is starting at http://127.0.0.1:8000  (Ctrl+C to stop)" -ForegroundColor Green
& $py -m uvicorn docketpilot.api.main:app --host 127.0.0.1 --port 8000
