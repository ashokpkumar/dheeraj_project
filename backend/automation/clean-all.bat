@echo off
REM clean-all.bat
REM Remove all automation containers and images

setlocal enabledelayedexpansion

echo.
echo ========================================
echo   Full Cleanup
echo ========================================
echo.
echo This will:
echo   1. Stop all automation containers
echo   2. Remove all automation containers
echo   3. Remove automation images
echo   4. Remove automation network
echo.
echo WARNING: This cannot be undone!
echo Press any key to continue or Ctrl+C to cancel...
pause >nul

echo.
echo Stopping all automation containers...
docker ps -q --filter "name=automation" | for /f %%i in ('findstr .') do (
    docker stop %%i >nul 2>&1
)

echo Removing all automation containers...
docker ps -aq --filter "name=automation" | for /f %%i in ('findstr .') do (
    docker rm %%i >nul 2>&1
)

echo Removing automation images...
docker images --format "{{.Repository}}:{{.Tag}}" | findstr "automation" | for /f %%i in ('findstr .') do (
    docker rmi %%i >nul 2>&1
)

echo Removing automation network...
docker network rm automation_network >nul 2>&1

echo.
echo ========================================
echo   Cleanup Complete
echo ========================================
echo.
echo Remaining containers:
docker ps -a --format "table {{.Names}}\t{{.Status}}"
echo.
echo Remaining images:
docker images --filter "dangling=false" --format "table {{.Repository}}:{{.Tag}}\t{{.Size}}"
echo.
pause
