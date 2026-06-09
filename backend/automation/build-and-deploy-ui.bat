@echo off
REM build-and-deploy-ui.bat
REM Build and deploy React UI container
REM Usage: build-and-deploy-ui.bat [command]
REM   command: build (build only), run (build & run), stop, start, logs, shell

setlocal enabledelayedexpansion

set COMMAND=%1
if "!COMMAND!"=="" set COMMAND=build

set UI_PATH=..\..\UI\my-react-flow-app
set IMAGE_NAME=automation:ui
set CONTAINER_NAME=automation_ui
set PORT=3000

echo.
echo ========================================
echo   React UI Build ^& Deploy
echo ========================================
echo.

REM Check if Docker is running
docker ps >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo ERROR: Docker is not running
    pause
    exit /b 1
)

REM Check if UI directory exists
if not exist "!UI_PATH!" (
    echo ERROR: UI directory not found: !UI_PATH!
    echo Please ensure you are in the backend/automation directory
    pause
    exit /b 1
)

echo UI Path: !UI_PATH!
echo Image: !IMAGE_NAME!
echo Container: !CONTAINER_NAME!
echo.

if "!COMMAND!"=="build" (
    goto build
) else if "!COMMAND!"=="run" (
    goto build_and_run
) else if "!COMMAND!"=="stop" (
    goto stop_container
) else if "!COMMAND!"=="start" (
    goto start_container
) else if "!COMMAND!"=="restart" (
    goto restart_container
) else if "!COMMAND!"=="logs" (
    goto view_logs
) else if "!COMMAND!"=="shell" (
    goto shell
) else if "!COMMAND!"=="remove" (
    goto remove_container
) else if "!COMMAND!"=="help" (
    goto show_help
) else (
    echo ERROR: Unknown command: !COMMAND!
    goto show_help
)

:show_help
echo Usage: build-and-deploy-ui.bat [command]
echo.
echo Commands:
echo   build              - Build React UI image only (default)
echo   run                - Build and run UI container
echo   stop               - Stop running UI container
echo   start              - Start stopped UI container
echo   restart            - Restart UI container
echo   logs               - View container logs
echo   shell              - Open shell in running container
echo   remove             - Remove UI container
echo   help               - Show this help message
echo.
echo Examples:
echo   build-and-deploy-ui.bat build
echo   build-and-deploy-ui.bat run
echo   build-and-deploy-ui.bat logs
echo.
pause
exit /b 0

:build
echo Building React UI image...
echo Command: docker build -t !IMAGE_NAME! !UI_PATH!
echo.
docker build -t !IMAGE_NAME! !UI_PATH!
if !ERRORLEVEL! neq 0 (
    echo ERROR: Build failed
    pause
    exit /b 1
)
echo.
echo Build completed successfully
echo.
echo Next steps:
echo   Run container: build-and-deploy-ui.bat run
echo   View logs:     build-and-deploy-ui.bat logs
echo.
pause
exit /b 0

:build_and_run
echo Building React UI image...
docker build -t !IMAGE_NAME! !UI_PATH!
if !ERRORLEVEL! neq 0 (
    echo ERROR: Build failed
    pause
    exit /b 1
)

echo.
echo Image built successfully, starting container...
echo.

REM Check if container exists and remove it
docker ps -a --format "{{.Names}}" | findstr /R "^!CONTAINER_NAME!$" >nul 2>&1
if %ERRORLEVEL% equ 0 (
    echo Stopping and removing existing container: !CONTAINER_NAME!
    docker stop !CONTAINER_NAME! >nul 2>&1
    docker rm !CONTAINER_NAME! >nul 2>&1
)

echo.
echo Starting React UI container...
docker run -d ^
    --name !CONTAINER_NAME! ^
    -p !PORT!:3000 ^
    --network automation_network ^
    !IMAGE_NAME!

if !ERRORLEVEL! equ 0 (
    echo.
    echo ========================================
    echo   React UI Started
    echo ========================================
    echo Container: !CONTAINER_NAME!
    echo Image: !IMAGE_NAME!
    echo Port: !PORT!
    echo URL: http://localhost:!PORT!
    echo.
    echo View logs: docker logs -f !CONTAINER_NAME!
    echo Stop:      docker stop !CONTAINER_NAME!
    echo.
) else (
    echo ERROR: Failed to start container
    pause
    exit /b 1
)

pause
exit /b 0

:stop_container
echo Stopping container: !CONTAINER_NAME!...
docker stop !CONTAINER_NAME!
if !ERRORLEVEL! equ 0 (
    echo Container stopped
) else (
    echo ERROR: Failed to stop container
)
pause
exit /b 0

:start_container
echo Starting container: !CONTAINER_NAME!...
docker start !CONTAINER_NAME!
if !ERRORLEVEL! equ 0 (
    echo Container started
    echo URL: http://localhost:!PORT!
) else (
    echo ERROR: Failed to start container
)
pause
exit /b 0

:restart_container
echo Restarting container: !CONTAINER_NAME!...
docker restart !CONTAINER_NAME!
if !ERRORLEVEL! equ 0 (
    echo Container restarted
    echo URL: http://localhost:!PORT!
) else (
    echo ERROR: Failed to restart container
)
pause
exit /b 0

:view_logs
echo.
echo Viewing logs for: !CONTAINER_NAME!
echo (Press Ctrl+C to stop)
echo.
docker logs -f !CONTAINER_NAME!
exit /b 0

:shell
echo Opening shell in: !CONTAINER_NAME!...
docker exec -it !CONTAINER_NAME! /bin/bash
exit /b 0

:remove_container
echo WARNING: This will remove the container
docker ps -a --format "{{.Names}}" | findstr /R "^!CONTAINER_NAME!$" >nul 2>&1
if %ERRORLEVEL% equ 0 (
    echo Removing container: !CONTAINER_NAME!...
    docker rm !CONTAINER_NAME!
    if !ERRORLEVEL! equ 0 (
        echo Container removed
    ) else (
        echo ERROR: Failed to remove container
    )
) else (
    echo Container not found
)
pause
exit /b 0
