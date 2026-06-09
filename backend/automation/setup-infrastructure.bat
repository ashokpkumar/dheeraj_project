@echo off
REM Setup script for automation infrastructure
REM Creates Docker network and starts Redis

echo.
echo ========================================
echo   Automation Infrastructure Setup
echo ========================================
echo.

REM Check if network exists
docker network inspect automation_network >nul 2>&1
if errorlevel 1 (
  echo Creating Docker network: automation_network...
  docker network create automation_network
  echo Docker network created
  echo.
) else (
  echo Docker network already exists: automation_network
  echo.
)

REM Check if Redis container exists
docker ps -a --format "{{.Names}}" | findstr /R "^automation_redis$" > nul
if not errorlevel 1 (
  echo Redis container already exists
  echo Checking if it's running...
  docker ps --format "{{.Names}}" | findstr /R "^automation_redis$" > nul
  if not errorlevel 1 (
    echo Redis is running
  ) else (
    echo Starting Redis...
    docker start automation_redis
  )
) else (
  echo Starting Redis container...
  docker run -d --name automation_redis ^
    -p 6379:6379 ^
    --network automation_network ^
    redis:7-alpine

  echo Redis container started
  echo Waiting for Redis to be ready...
  timeout /t 3 /nobreak
)

echo.
echo ========================================
echo   Infrastructure Ready
echo ========================================
echo Network: automation_network
echo Redis: automation_redis (port 6379)
echo.
echo Next steps:
echo   1. Update your .env file with database credentials
echo   2. Build services: .\build-and-deploy.bat orchestrator main serve
echo   3. Run migrations: docker exec -it automation_main python manage.py migrate
echo.
