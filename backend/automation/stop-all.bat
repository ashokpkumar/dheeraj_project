@echo off
REM stop-all.bat
REM Stop all automation containers

setlocal enabledelayedexpansion

echo.
echo ========================================
echo   Stopping All Containers
echo ========================================
echo.

docker ps -q --filter "name=automation" | findstr . >nul
if %ERRORLEVEL% equ 0 (
    echo Stopping containers...
    docker ps -q --filter "name=automation" | for /f %%i in ('findstr .') do docker stop %%i
    echo All containers stopped
) else (
    echo No running automation containers found
)

echo.
docker ps -a --filter "name=automation" --format "table {{.Names}}\t{{.Status}}"
echo.
pause
