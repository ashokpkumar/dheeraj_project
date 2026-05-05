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
echo   1. Redis (if not running)
echo   2. Orchestrator API (port 8000)
echo   3. Celery Worker
echo   4. Celery Beat Scheduler
echo   5. React UI (port 3000)
echo   6. Flower Monitoring (port 5555)
echo.
echo Press any key to continue or Ctrl+C to cancel...
pause >nul

echo.
echo [1/6] Setting up infrastructure...
call setup-infrastructure.bat
if %ERRORLEVEL% neq 0 (
    echo ERROR: Infrastructure setup failed
    pause
    exit /b 1
)

echo.
echo [2/6] Building Orchestrator...
call build-and-deploy.bat orchestrator main serve
if %ERRORLEVEL% neq 0 (
    echo ERROR: Orchestrator build failed
    pause
    exit /b 1
)

echo.
echo [3/6] Building Worker...
call build-and-deploy.bat worker w1 worker
if %ERRORLEVEL% neq 0 (
    echo ERROR: Worker build failed
    pause
    exit /b 1
)

echo.
echo [4/6] Building Beat Scheduler...
call build-and-deploy.bat orchestrator scheduler beat
if %ERRORLEVEL% neq 0 (
    echo ERROR: Beat build failed
    pause
    exit /b 1
)

echo.
echo [5/6] Building React UI...
call build-and-deploy-ui.bat run
if %ERRORLEVEL% neq 0 (
    echo ERROR: UI build/start failed
    pause
    exit /b 1
)

echo.
echo [6/6] Building Flower...
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
