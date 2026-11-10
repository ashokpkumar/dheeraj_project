@echo off
rem One-step deploy for the Windows VM: pull main, install deps, migrate,
rem then serve backend (port 8000) and prebuilt frontend (port 8080) with Waitress.
rem The whole script is one parenthesized block so cmd parses it fully before
rem running; this keeps it safe even if "git pull" rewrites this file.
(
    setlocal
    set "ROOT=%~dp0"
    set "BACKEND_DIR=%~dp0backend\automation"

    where git >nul 2>nul
    if errorlevel 1 (
        echo ERROR: git was not found on PATH.
        pause
        exit /b 1
    )

    echo === Pulling latest main ===
    pushd "%~dp0"
    git fetch origin main
    if errorlevel 1 (
        echo ERROR: git fetch failed.
        pause
        exit /b 1
    )
    git checkout main
    if errorlevel 1 (
        echo ERROR: could not switch to main. Commit or discard local changes first.
        pause
        exit /b 1
    )
    git pull --ff-only origin main
    if errorlevel 1 (
        echo ERROR: git pull failed. Resolve local changes/conflicts and retry.
        pause
        exit /b 1
    )
    popd

    if not exist "%BACKEND_DIR%\manage.py" (
        echo ERROR: Could not find backend\automation\manage.py.
        pause
        exit /b 1
    )
    if not exist "%~dp0UI\my-react-flow-app\dist\index.html" (
        echo ERROR: UI build not found at UI\my-react-flow-app\dist. It must be committed to main.
        pause
        exit /b 1
    )

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
            echo ERROR: Could not create the virtual environment. Is Python installed?
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
    python manage.py makemigrations
    if errorlevel 1 (
        echo ERROR: makemigrations failed.
        pause
        exit /b 1
    )
    python manage.py migrate
    if errorlevel 1 (
        echo ERROR: migrate failed.
        pause
        exit /b 1
    )

    echo === Starting servers ===
    python serve_all.py
    if errorlevel 1 (
        echo ERROR: Server exited with an error.
        pause
        exit /b 1
    )
    exit /b 0
)
