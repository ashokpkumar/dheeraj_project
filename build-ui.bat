@echo off
setlocal

set "UI_DIR=%~dp0UI\my-react-flow-app"

rem Use the portable Node.js (zip install) if it exists, ahead of any older system Node.
if not defined NODE_PORTABLE_DIR set "NODE_PORTABLE_DIR=C:\tools\node"
if exist "%NODE_PORTABLE_DIR%\node.exe" (
    set "PATH=%NODE_PORTABLE_DIR%;%PATH%"
    echo Using portable Node.js from %NODE_PORTABLE_DIR%
)
call node -v
call npm -v

where npm >nul 2>nul
if errorlevel 1 (
    echo ERROR: npm was not found. Install Node.js on the build machine first.
    pause
    exit /b 1
)

pushd "%UI_DIR%"
if errorlevel 1 (
    echo ERROR: Could not find the UI project at "%UI_DIR%".
    pause
    exit /b 1
)

echo Installing UI dependencies from package-lock.json...
call npm ci
if errorlevel 1 goto failed

rem Workaround for npm optional-dependency bug (https://github.com/npm/cli/issues/4828):
rem older npm versions can skip rollup's platform-specific native package.
if not exist "node_modules\@rollup\rollup-win32-x64-msvc" (
    echo Rollup native package missing, installing it explicitly...
    call npm install --no-save --no-package-lock @rollup/rollup-win32-x64-msvc@4.57.1
    if errorlevel 1 goto failed
)

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
pause
exit /b %BUILD_EXIT_CODE%