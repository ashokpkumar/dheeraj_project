param(
    [int]$Port = 5555,
    [string]$BindAddress = "0.0.0.0"
)

Write-Host "Starting Windows Automation Service..." -ForegroundColor Cyan

if (-Not (Test-Path "windows_automation_service.py")) {
    Write-Host "ERROR: windows_automation_service.py not found in current directory" -ForegroundColor Red
    exit 1
}

try {
    $pythonVersion = python --version 2>&1
    Write-Host "Python found: $pythonVersion" -ForegroundColor Green
} catch {
    Write-Host "ERROR: Python not found." -ForegroundColor Red
    exit 1
}

$extraRunning = Get-Process | Where-Object {$_.ProcessName -like "*EXTRA*"}
if ($extraRunning) {
    Write-Host "EXTRA emulator is running" -ForegroundColor Green
} else {
    Write-Host "WARNING: EXTRA emulator not detected" -ForegroundColor Yellow
    Write-Host "Please start EXTRA emulator with active sessions" -ForegroundColor Yellow
}

Write-Host "Checking Python dependencies..." -ForegroundColor Cyan

$requiredPackages = @(
    @{Name="flask"; Import="flask"; Install="flask"},
    @{Name="flask_cors"; Import="flask_cors"; Install="flask-cors"},
    @{Name="pywin32"; Import="win32com.client"; Install="pywin32"}
)

foreach ($package in $requiredPackages) {
    try {
        python -c "import $($package.Import)" 2>$null
        if ($LASTEXITCODE -eq 0) {
            Write-Host "OK: $($package.Name) installed" -ForegroundColor Green
        } else {
            throw "Import failed"
        }
    } catch {
        Write-Host "MISSING: $($package.Name) not installed" -ForegroundColor Red
        Write-Host "  Run: pip install $($package.Install)" -ForegroundColor Yellow
    }
}

Write-Host "Configuration:" -ForegroundColor Cyan
Write-Host "  Host: $BindAddress" -ForegroundColor Cyan
Write-Host "  Port: $Port" -ForegroundColor Cyan

$env:WINDOWS_SERVICE_HOST = $BindAddress
$env:WINDOWS_SERVICE_PORT = $Port

Write-Host "Service will be available at: http://localhost:$Port" -ForegroundColor Green
Write-Host "Press Ctrl+C to stop" -ForegroundColor Cyan

python windows_automation_service.py
