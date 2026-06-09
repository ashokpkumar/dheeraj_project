# quick-start.ps1
# PowerShell version of quick-start.bat
# Quick start all services

Write-Host "`n========================================" -ForegroundColor Green
Write-Host "   Quick Start - All Services" -ForegroundColor Green
Write-Host "========================================`n" -ForegroundColor Green

Write-Host "This will start:" -ForegroundColor Cyan
Write-Host "  1. Redis (if not running)"
Write-Host "  2. Orchestrator API (port 8000)"
Write-Host "  3. Celery Worker"
Write-Host "  4. Celery Beat Scheduler"
Write-Host "  5. React UI (port 3000)"
Write-Host "  6. Flower Monitoring (port 5555)`n"

Read-Host "Press Enter to continue or Ctrl+C to cancel"

$steps = @(
    @{Step=1; Name="Setting up infrastructure"; Command="& '.\setup-infrastructure.bat'"},
    @{Step=2; Name="Building Orchestrator"; Command="& '.\build-and-deploy.bat' orchestrator main serve"},
    @{Step=3; Name="Building Worker"; Command="& '.\build-and-deploy.bat' worker w1 worker"},
    @{Step=4; Name="Building Beat Scheduler"; Command="& '.\build-and-deploy.bat' orchestrator scheduler beat"},
    @{Step=5; Name="Building React UI"; Command="& '.\build-and-deploy-ui.ps1' run"},
    @{Step=6; Name="Building Flower"; Command="& '.\build-and-deploy.bat' orchestrator flower flower"}
)

foreach ($step in $steps) {
    Write-Host "`n[$($step.Step)/6] $($step.Name)..." -ForegroundColor Yellow
    Invoke-Expression $step.Command
    if ($LASTEXITCODE -ne 0) {
        Write-Host "ERROR: $($step.Name) failed" -ForegroundColor Red
        exit 1
    }
}

Write-Host "`n========================================" -ForegroundColor Green
Write-Host "   All Services Started" -ForegroundColor Green
Write-Host "========================================`n" -ForegroundColor Green

Write-Host "Access services at:" -ForegroundColor Cyan
Write-Host "  Frontend:   http://localhost:3000"
Write-Host "  API:        http://localhost:8000"
Write-Host "  Admin:      http://localhost:8000/admin"
Write-Host "  Flower:     http://localhost:5555"
Write-Host "  Redis CLI:  docker exec -it automation_redis redis-cli`n"

Write-Host "View logs:" -ForegroundColor Cyan
Write-Host "  .\view-logs.ps1 main"
Write-Host "  .\view-logs.ps1 worker"
Write-Host "  .\view-logs.ps1 beat"
Write-Host "  .\view-logs.ps1 ui`n"

Read-Host "Press Enter to exit"
