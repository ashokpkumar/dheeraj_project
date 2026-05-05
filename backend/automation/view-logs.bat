@echo off
REM view-logs.bat
REM View logs from automation containers

setlocal enabledelayedexpansion

if "%1"=="" (
    echo Usage: view-logs.bat [container]
    echo.
    echo Available containers:
    echo   main      - Orchestrator API
    echo   worker    - Celery Worker (w1)
    echo   beat      - Celery Beat Scheduler
    echo   flower    - Flower Monitoring
    echo   ui        - React Frontend
    echo   redis     - Redis
    echo   all       - All containers (show status only)
    echo.
    echo Examples:
    echo   view-logs.bat main
    echo   view-logs.bat worker
    echo   view-logs.bat all
    echo.
    docker ps -a --filter "name=automation" --format "table {{.Names}}\t{{.Status}}"
    echo.
    pause
    exit /b 0
)

set CONTAINER=%1

if "!CONTAINER!"=="all" (
    echo.
    echo ========================================
    echo   Automation Containers Status
    echo ========================================
    echo.
    docker ps -a --filter "name=automation" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
    echo.
    pause
    exit /b 0
)

if "!CONTAINER!"=="main" (
    set CONTAINER_NAME=automation_main
) else if "!CONTAINER!"=="worker" (
    set CONTAINER_NAME=automation_worker_w1
) else if "!CONTAINER!"=="beat" (
    set CONTAINER_NAME=automation_beat
) else if "!CONTAINER!"=="flower" (
    set CONTAINER_NAME=automation_flower
) else if "!CONTAINER!"=="ui" (
    set CONTAINER_NAME=automation_ui
) else if "!CONTAINER!"=="redis" (
    set CONTAINER_NAME=automation_redis
) else (
    set CONTAINER_NAME=!CONTAINER!
)

echo.
echo Viewing logs for: !CONTAINER_NAME!
echo (Press Ctrl+C to stop)
echo.

docker logs -f !CONTAINER_NAME!
