@echo off
REM Docker Build and Deploy Helper for Windows
REM Usage:
REM   build-and-deploy.bat orchestrator orchestrator_main
REM   build-and-deploy.bat worker worker_1
REM   build-and-deploy.bat worker worker_2

setlocal enabledelayedexpansion

REM Arguments
set ROLE=%~1
set NODE_NAME=%~2
set COMMAND=%~3

REM Defaults
if "%ROLE%"=="" set ROLE=orchestrator
if "%NODE_NAME%"=="" set NODE_NAME=%ROLE%_1
if "%COMMAND%"=="" set COMMAND=serve

REM Validate role
if not "%ROLE%"=="orchestrator" if not "%ROLE%"=="worker" (
  echo Error: Role must be 'orchestrator' or 'worker'
  echo Usage: build-and-deploy.bat ^<role^> ^<node_name^> [command]
  echo   Roles: orchestrator, worker
  echo   Commands: serve, worker, beat, flower, shell, config
  exit /b 1
)

REM Set IS_ORCHESTRATOR based on role
if "%ROLE%"=="orchestrator" (
  set IS_ORCHESTRATOR=True
) else (
  set IS_ORCHESTRATOR=False
)

set IMAGE_NAME=automation:%ROLE%

REM Build container name with command suffix for special services
set CONTAINER_NAME=automation_%NODE_NAME%
if "%COMMAND%"=="beat" set CONTAINER_NAME=automation_%NODE_NAME%_beat
if "%COMMAND%"=="flower" set CONTAINER_NAME=automation_%NODE_NAME%_flower
if "%COMMAND%"=="worker" set CONTAINER_NAME=automation_%NODE_NAME%_worker

echo.
echo ========================================
echo   Docker Build ^& Deploy
echo ========================================
echo Role: %ROLE%
echo Node Name: %NODE_NAME%
echo Container Name: %CONTAINER_NAME%
echo Image Name: %IMAGE_NAME%
echo IS_ORCHESTRATOR: %IS_ORCHESTRATOR%
echo Command: %COMMAND%
echo.

REM Step 1: Build Docker image
echo Step 1: Building Docker image...
docker build ^
  --build-arg ROLE=%ROLE% ^
  --build-arg NODE_NAME=%NODE_NAME% ^
  --build-arg IS_ORCHESTRATOR=%IS_ORCHESTRATOR% ^
  -t %IMAGE_NAME% ^
  .

if errorlevel 1 (
  echo Error: Docker build failed
  exit /b 1
)

echo Docker image built: %IMAGE_NAME%
echo.

REM Step 2: Stop existing container if running
docker ps -a --format "{{.Names}}" | findstr /R "^%CONTAINER_NAME%$" > nul
if not errorlevel 1 (
  echo Step 2: Stopping existing container...
  docker stop %CONTAINER_NAME% >nul 2>&1 || true
  docker rm %CONTAINER_NAME% >nul 2>&1 || true
  echo Existing container stopped and removed
  echo.
) else (
  echo Step 2: No existing container found
  echo.
)

REM Step 3: Run container
echo Step 3: Starting new container...

if "%COMMAND%"=="serve" (
  docker run -d ^
    --name %CONTAINER_NAME% ^
    -p 8000:8000 ^
    --env-file .env ^
    -e ROLE=%ROLE% ^
    -e NODE_NAME=%NODE_NAME% ^
    -e IS_ORCHESTRATOR=%IS_ORCHESTRATOR% ^
    --network automation_network ^
    -v %cd%:/app ^
    %IMAGE_NAME% ^
    serve
  
  echo Container started in API server mode
  echo API Available at: http://localhost:8000
  
) else if "%COMMAND%"=="worker" (
  docker run -d ^
    --name %CONTAINER_NAME% ^
    --env-file .env ^
    -e ROLE=%ROLE% ^
    -e NODE_NAME=%NODE_NAME% ^
    -e IS_ORCHESTRATOR=%IS_ORCHESTRATOR% ^
    --network automation_network ^
    -v %cd%:/app ^
    %IMAGE_NAME% ^
    worker
  
  echo Container started in Celery worker mode
  
) else if "%COMMAND%"=="beat" (
  if not "%IS_ORCHESTRATOR%"=="True" (
    echo Error: Celery Beat can only run in orchestrator mode
    exit /b 1
  )
  
  docker run -d ^
    --name %CONTAINER_NAME% ^
    --env-file .env ^
    -e ROLE=%ROLE% ^
    -e NODE_NAME=%NODE_NAME% ^
    -e IS_ORCHESTRATOR=%IS_ORCHESTRATOR% ^
    --network automation_network ^
    -v %cd%:/app ^
    %IMAGE_NAME% ^
    beat
  
  echo Container started in Celery Beat scheduler mode
  
) else if "%COMMAND%"=="flower" (
  docker run -d ^
    --name %CONTAINER_NAME% ^
    -p 5555:5555 ^
    --env-file .env ^
    -e ROLE=%ROLE% ^
    -e NODE_NAME=%NODE_NAME% ^
    -e IS_ORCHESTRATOR=%IS_ORCHESTRATOR% ^
    --network automation_network ^
    -v %cd%:/app ^
    %IMAGE_NAME% ^
    flower
  
  echo Container started in Flower monitoring mode
  echo Flower UI Available at: http://localhost:5555
  
) else (
  docker run -d ^
    --name %CONTAINER_NAME% ^
    --env-file .env ^
    -e ROLE=%ROLE% ^
    -e NODE_NAME=%NODE_NAME% ^
    -e IS_ORCHESTRATOR=%IS_ORCHESTRATOR% ^
    --network automation_network ^
    -v %cd%:/app ^
    %IMAGE_NAME% ^
    %COMMAND%
  
  echo Container started with command: %COMMAND%
)

if errorlevel 1 (
  echo Error: Docker run failed
  exit /b 1
)

echo.
echo ========================================
echo   Container Details
echo ========================================
for /f "tokens=*" %%A in ('docker ps --format "{{.Names}} {{.Status}}" ^| findstr %CONTAINER_NAME%') do set STATUS=%%A
echo Container Name: %CONTAINER_NAME%
echo Image: %IMAGE_NAME%
echo Status: %STATUS%
echo.
echo Useful Commands:
echo   View logs:    docker logs -f %CONTAINER_NAME%
echo   Stop:         docker stop %CONTAINER_NAME%
echo   Start:        docker start %CONTAINER_NAME%
echo   Remove:       docker rm %CONTAINER_NAME%
echo   Shell:        docker exec -it %CONTAINER_NAME% bash
echo.

endlocal
