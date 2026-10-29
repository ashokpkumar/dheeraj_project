@echo off
cd /d "%~dp0UI\my-react-flow-app\dist"
if errorlevel 1 (
    echo ERROR: UI build output not found. Run build-ui.bat first.
    pause
    exit /b 1
)

python -m http.server 8080