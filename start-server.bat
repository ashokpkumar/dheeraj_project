@echo off
rem One-step deploy for the Windows VM. Push to GitHub, then run this on the VM:
rem   1. pull latest main (VM copy is reset to match GitHub exactly)
rem   2. build the React UI
rem   3. create venv, install Python packages, apply migrations
rem   4. serve backend (port 8000) and UI (port 8080) with Waitress
rem The whole script is one parenthesized block so cmd parses it fully before
rem running; this keeps it safe even if "git pull" rewrites this file.
(
    setlocal
    set "ROOT=%~dp0"
    set "BACKEND_DIR=%~dp0backend\automation"
    set "UI_DIR=%~dp0UI\my-react-flow-app"

    where git >nul 2>nul
    if errorlevel 1 (
        echo ERROR: git was not found. Install Git for Windows from https://git-scm.com then run this again.
        pause
        exit /b 1
    )

    where py >nul 2>nul
    if errorlevel 1 (
        where python >nul 2>nul
        if errorlevel 1 (
            echo Python was not found. Trying to install it with winget...
            where winget >nul 2>nul
            if errorlevel 1 (
                echo ERROR: Install Python 3 from https://python.org then run this again.
                pause
                exit /b 1
            )
            winget install -e --id Python.Python.3.13 --accept-package-agreements --accept-source-agreements
            echo Python installed. Close this window, open a NEW one and run this script again.
            pause
            exit /b 0
        )
    )

    where npm >nul 2>nul
    if errorlevel 1 (
        echo Node.js was not found. Trying to install it with winget...
        where winget >nul 2>nul
        if errorlevel 1 (
            echo ERROR: Install Node.js LTS from https://nodejs.org then run this again.
            pause
            exit /b 1
        )
        winget install -e --id OpenJS.NodeJS.LTS --accept-package-agreements --accept-source-agreements
        echo Node.js installed. Close this window, open a NEW one and run this script again.
        pause
        exit /b 0
    )

    echo === Pulling latest main ===
    pushd "%~dp0"
    git fetch origin main
    if errorlevel 1 (
        echo ERROR: git fetch failed. Check the network and git credentials.
        pause
        exit /b 1
    )
    git checkout -f main
    if errorlevel 1 (
        echo ERROR: could not switch to main.
        pause
        exit /b 1
    )
    rem Make the VM match GitHub exactly. Untracked files such as .env and .venv are kept.
    git reset --hard origin/main
    if errorlevel 1 (
        echo ERROR: git reset failed.
        pause
        exit /b 1
    )
    popd

    if not exist "%BACKEND_DIR%\manage.py" (
        echo ERROR: Could not find backend\automation\manage.py.
        pause
        exit /b 1
    )

    echo === Building UI ===
    pushd "%UI_DIR%"
    call npm ci
    if errorlevel 1 (
        echo ERROR: npm ci failed.
        pause
        exit /b 1
    )
    call npm run build
    if errorlevel 1 (
        echo ERROR: UI build failed.
        pause
        exit /b 1
    )
    popd

    pushd "%BACKEND_DIR%"

    if not exist ".venv\Scripts\python.exe" (
        echo === Creating virtual environment ===
        where py >nul 2>nul
        if not errorlevel 1 (
            py -3 -m venv .venv
        ) else (
            python -m venv .venv
        )
        if errorlevel 1 (
            echo ERROR: Could not create the virtual environment.
            pause
            exit /b 1
        )
    )

    call ".venv\Scripts\activate.bat"
    if errorlevel 1 (
        echo ERROR: Could not activate the virtual environment.
        pause
        exit /b 1
    )

    echo === Installing Python packages ===
    python -m pip install --upgrade pip
    python -m pip install -r requirements.txt
    if errorlevel 1 (
        echo ERROR: pip install failed.
        pause
        exit /b 1
    )

    echo === Applying migrations ===
    python manage.py migrate --noinput
    if errorlevel 1 (
        echo ERROR: migrate failed.
        pause
        exit /b 1
    )

    echo === Starting servers - keep this window open ===
    python serve_all.py
    if errorlevel 1 (
        echo ERROR: Server exited with an error.
        pause
        exit /b 1
    )
    exit /b 0
)
