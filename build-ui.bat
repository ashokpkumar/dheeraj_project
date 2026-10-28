@echo off
setlocal

set "UI_DIR=%~dp0UI\my-react-flow-app"

where npm >nul 2>nul
if errorlevel 1 (
    echo ERROR: npm was not found. Install Node.js on the build machine first.
    exit /b 1
)

pushd "%UI_DIR%"
if errorlevel 1 (
    echo ERROR: Could not find the UI project at "%UI_DIR%".
    exit /b 1
)

echo Installing UI dependencies from package-lock.json...
call npm ci
if errorlevel 1 goto failed

echo Building the production UI...
call npm run build
if errorlevel 1 goto failed

popd
echo.
echo UI build complete: UI\my-react-flow-app\dist
echo The dist folder is ignored by Git. To include it in a commit, run:
echo   git add -f UI/my-react-flow-app/dist
exit /b 0

:failed
set "BUILD_EXIT_CODE=%ERRORLEVEL%"
popd
echo ERROR: UI build failed with exit code %BUILD_EXIT_CODE%.
exit /b %BUILD_EXIT_CODE%