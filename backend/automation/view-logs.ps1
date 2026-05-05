# view-logs.ps1
# PowerShell version of view-logs.bat
# View logs from automation containers

param(
    [string]$Container = ""
)

if ([string]::IsNullOrWhiteSpace($Container)) {
    Write-Host "`nUsage: .\view-logs.ps1 [container]`n" -ForegroundColor Cyan
    Write-Host "Available containers:" -ForegroundColor Cyan
    Write-Host "  main      - Orchestrator API"
    Write-Host "  worker    - Celery Worker (w1)"
    Write-Host "  beat      - Celery Beat Scheduler"
    Write-Host "  flower    - Flower Monitoring"
    Write-Host "  ui        - React Frontend"
    Write-Host "  redis     - Redis"
    Write-Host "  all       - All containers (show status only)`n"
    
    Write-Host "Examples:" -ForegroundColor Cyan
    Write-Host "  .\view-logs.ps1 main"
    Write-Host "  .\view-logs.ps1 worker"
    Write-Host "  .\view-logs.ps1 all`n"
    
    Write-Host "Current containers:" -ForegroundColor Cyan
    Write-Host "----------------------------------------"
    docker ps -a --filter "name=automation" --format "table {{.Names}}`t{{.Status}}"
    Write-Host ""
    exit 0
}

if ($Container -eq "all") {
    Write-Host "`n========================================" -ForegroundColor Green
    Write-Host "   Automation Containers Status" -ForegroundColor Green
    Write-Host "========================================`n" -ForegroundColor Green
    docker ps -a --filter "name=automation" --format "table {{.Names}}`t{{.Status}}`t{{.Ports}}"
    Write-Host ""
    exit 0
}

$containerMap = @{
    "main"   = "automation_main"
    "worker" = "automation_worker_w1"
    "beat"   = "automation_beat"
    "flower" = "automation_flower"
    "ui"     = "automation_ui"
    "redis"  = "automation_redis"
}

if ($containerMap.ContainsKey($Container)) {
    $containerName = $containerMap[$Container]
} else {
    $containerName = $Container
}

Write-Host "`nViewing logs for: $containerName" -ForegroundColor Cyan
Write-Host "(Press Ctrl+C to stop)`n"

docker logs -f $containerName
