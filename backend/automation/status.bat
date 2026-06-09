@echo off
REM status.bat
REM Show status of all automation containers and services

setlocal enabledelayedexpansion

echo.
echo ========================================
echo   Automation Platform Status
echo ========================================
echo.

REM Check Docker
docker --version >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo ERROR: Docker not available
) else (
    echo ✓ Docker is available
)

echo.
echo Containers:
echo ----------------------------------------
docker ps -a --filter "name=automation" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" 2>nul || (
    echo ERROR: Could not list containers
)

echo.
echo Network:
echo ----------------------------------------
docker network inspect automation_network >nul 2>&1
if %ERRORLEVEL% equ 0 (
    echo ✓ automation_network exists
) else (
    echo ✗ automation_network NOT found
)

echo.
echo Redis:
echo ----------------------------------------
docker exec automation_redis redis-cli ping >nul 2>&1
if %ERRORLEVEL% equ 0 (
    echo ✓ Redis is responding
) else (
    echo ✗ Redis is NOT responding
)

echo.
echo Services Accessibility:
echo ----------------------------------------
echo API (8000):    docker exec automation_main python manage.py show_config
echo Redis (6379):  docker exec automation_redis redis-cli info
echo Worker:        docker logs automation_worker_w1 --tail 1
echo Beat:          docker logs automation_beat --tail 1
echo UI (3000):     docker exec automation_ui ls /usr/share/nginx/html
echo Flower (5555): docker logs automation_flower --tail 1

echo.
echo URLs:
echo ----------------------------------------
echo Frontend:   http://localhost:3000
echo API:        http://localhost:8000
echo Admin:      http://localhost:8000/admin
echo Flower:     http://localhost:5555

echo.
pause
