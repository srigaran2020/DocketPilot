# Run every quality check (replaces CI, since this project does not use git/GitHub).
#   .\check.ps1          lint + type check + all tests (Docker stack must be running for integration tests)
#   .\check.ps1 -Live    also run the tests that call the real Groq API
param([switch]$Live)

$py = ".\.venv\Scripts\python.exe"
$failed = @()

Write-Host "`n== Lint (ruff)" -ForegroundColor Cyan
& $py -m ruff check docketpilot tests migrations
if ($LASTEXITCODE -ne 0) { $failed += "lint" }

Write-Host "`n== Type check (mypy)" -ForegroundColor Cyan
& $py -m mypy
if ($LASTEXITCODE -ne 0) { $failed += "types" }

Write-Host "`n== Tests (pytest)" -ForegroundColor Cyan
$marker = if ($Live) { "live or not live" } else { "not live" }
& $py -m pytest -m $marker --cov=docketpilot --cov-report=term-missing:skip-covered -q
if ($LASTEXITCODE -ne 0) { $failed += "tests" }

if ($failed.Count -eq 0) {
    Write-Host "`nALL CHECKS PASSED" -ForegroundColor Green
    exit 0
}
Write-Host "`nFAILED: $($failed -join ', ')" -ForegroundColor Red
exit 1
