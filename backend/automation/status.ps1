# status.ps1
# PowerShell version of status.bat
# Show status of all automation containers

Write-Host "`n========================================" -ForegroundColor Green
Write-Host "   Automation Platform Status" -ForegroundColor Green
Write-Host "========================================`n" -ForegroundColor Green

# Check Docker
try {
    $version = docker --version 2>&1
    Write-Host "✓ Docker is available" -ForegroundColor Green
    Write-Host "  $version`n"
} catch {
    Write-Host "✗ Docker not available" -ForegroundColor Red
}

# Show containers
Write-Host "Containers:" -ForegroundColor Cyan
Write-Host "----------------------------------------"
docker ps -a --filter "name=automation" --format "table {{.Names}}`t{{.Status}}`t{{.Ports}}" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Could not list containers" -ForegroundColor Red
}

# Check network
Write-Host "`nNetwork:" -ForegroundColor Cyan
Write-Host "----------------------------------------"
if (docker network inspect automation_network 2>$null) {
    Write-Host "✓ automation_network exists" -ForegroundColor Green
} else {
    Write-Host "✗ automation_network NOT found" -ForegroundColor Red
}

# Check Redis
Write-Host "`nRedis:" -ForegroundColor Cyan
Write-Host "----------------------------------------"
if (docker exec automation_redis redis-cli ping 2>$null) {
    Write-Host "✓ Redis is responding" -ForegroundColor Green
} else {
    Write-Host "✗ Redis is NOT responding" -ForegroundColor Red
}

# Service URLs
Write-Host "`nService URLs:" -ForegroundColor Cyan
Write-Host "----------------------------------------"
Write-Host "Frontend:   http://localhost:3001"
Write-Host "API:        http://localhost:8000"
Write-Host "Admin:      http://localhost:8000/admin"
Write-Host "Flower:     http://localhost:5555"
Write-Host "Redis:      localhost:6379`n"

# Quick actions
Write-Host "Quick Actions:" -ForegroundColor Cyan
Write-Host "  .\view-logs.ps1 main     - View API logs"
Write-Host "  .\view-logs.ps1 worker   - View worker logs"
Write-Host "  .\view-logs.ps1 beat     - View scheduler logs"
Write-Host "  .\stop-all.bat          - Stop all containers"
Write-Host "  .\quick-start.ps1       - Start everything`n"

Read-Host "Press Enter to exit"
