@echo off
REM quick-start.bat
REM Quick start all services (setup, orchestrator, worker, beat, ui, flower)

setlocal enabledelayedexpansion

echo.
echo ========================================
echo   Quick Start - All Services
echo ========================================
echo.
echo This will start:
echo   1. Infrastructure (Redis, Network)
echo   2. Windows Automation Service
echo   3. Orchestrator API (port 8000)
echo   4. Celery Worker
echo   5. Celery Beat Scheduler
echo   6. React UI (port 3000)
echo   7. Flower Monitoring (port 5555)
echo.
echo Press any key to continue or Ctrl+C to cancel...
pause >nul

echo.
echo [1/7] Setting up infrastructure...
call setup-infrastructure.bat
if %ERRORLEVEL% neq 0 (
    echo ERROR: Infrastructure setup failed
    pause
    exit /b 1
)

echo.
echo [2/7] Setting up Windows Automation Service...
echo.
echo Installing Python dependencies...
pip install pywin32 flask flask-cors
if %ERRORLEVEL% neq 0 (
    echo ERROR: Failed to install Python dependencies
    pause
    exit /b 1
)

echo.
echo Post-installing pywin32...
python -m pip install --force-reinstall --no-cache-dir pywin32
if %ERRORLEVEL% neq 0 (
    echo ERROR: Failed to post-install pywin32
    pause
    exit /b 1
)

echo.
echo Make sure EXTRA emulator is running with sessions!
echo.
pause /PROMPT "Press any key when EXTRA emulator is ready..."

echo.
echo Starting Windows Automation Service...
powershell -ExecutionPolicy Bypass -File .\start-windows-service.ps1
if %ERRORLEVEL% neq 0 (
    echo ERROR: Failed to start Windows Automation Service
    pause
    exit /b 1
)

echo.
echo Testing Windows Automation Service health...
timeout /t 2 /nobreak
powershell -Command "try { $response = Invoke-WebRequest -Uri 'http://localhost:5555/health' -ErrorAction Stop; Write-Host 'Service is healthy!' } catch { Write-Host 'ERROR: Service health check failed'; exit 1 }"
if %ERRORLEVEL% neq 0 (
    echo ERROR: Windows Automation Service health check failed
    pause
    exit /b 1
)

echo ✓ Windows Automation Service is running at http://localhost:5555
echo.

echo.
echo [3/7] Building Orchestrator...
call build-and-deploy.bat orchestrator main serve
if %ERRORLEVEL% neq 0 (
    echo ERROR: Orchestrator build failed
    pause
    exit /b 1
)

echo.
echo [4/7] Building Worker...
call build-and-deploy.bat worker w1 worker
if %ERRORLEVEL% neq 0 (
    echo ERROR: Worker build failed
    pause
    exit /b 1
)

echo.
echo [5/7] Building Beat Scheduler...
call build-and-deploy.bat orchestrator scheduler beat
if %ERRORLEVEL% neq 0 (
    echo ERROR: Beat build failed
    pause
    exit /b 1
)

echo.
echo [6/7] Building React UI...
call build-and-deploy-ui.bat run
if %ERRORLEVEL% neq 0 (
    echo ERROR: UI build/start failed
    pause
    exit /b 1
)

echo.
echo [7/7] Building Flower...
call build-and-deploy.bat orchestrator flower flower
if %ERRORLEVEL% neq 0 (
    echo ERROR: Flower build failed
    pause
    exit /b 1
)

echo.
echo ========================================
echo   All Services Started
echo ========================================
echo.
echo Access services at:
echo   Frontend:   http://localhost:3000
echo   API:        http://localhost:8000
echo   Admin:      http://localhost:8000/admin
echo   Flower:     http://localhost:5555
echo   Redis CLI:  docker exec -it automation_redis redis-cli
echo.
echo View logs:
echo   docker logs -f automation_main
echo   docker logs -f automation_worker_w1
echo   docker logs -f automation_beat
echo   docker logs -f automation_ui
echo   docker logs -f automation_flower
echo.
pause
