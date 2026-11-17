@echo off
rem One-step deploy for the Windows VM. Push to GitHub, then run this on the VM:
rem   1. pull latest main (VM copy is reset to match GitHub exactly)
rem   2. check the prebuilt UI (dist) that came with the pull
rem   3. create venv, install Python packages, apply migrations
rem   4. serve backend (port 8000) and UI (port 8080) with Waitress
rem
rem IMPORTANT: the whole script is one parenthesized block so cmd parses it fully
rem before running; this keeps it safe even if "git reset" rewrites this file.
rem Inside a block, %VAR% is expanded at PARSE time, so a variable set inside the
rem block reads as empty. Use !VAR! (delayed expansion) for those, and %~dp0 for paths.
(
    setlocal EnableDelayedExpansion

    echo.
    echo [!time:~0,8!] ================= DEPLOY START =================
    echo [!time:~0,8!] Script folder : %~dp0
    echo [!time:~0,8!] Backend folder: %~dp0backend\automation
    echo [!time:~0,8!] UI folder     : %~dp0UI\my-react-flow-app
    echo [!time:~0,8!] Running as    : %USERNAME% on %COMPUTERNAME%

    echo.
    echo [!time:~0,8!] [1/6] Checking required tools
    where git >nul 2>nul
    if errorlevel 1 (
        echo [!time:~0,8!] ERROR: git was not found. Install Git for Windows from https://git-scm.com then run this again.
        pause
        exit /b 1
    )
    for /f "delims=" %%v in ('git --version') do echo [!time:~0,8!]   git    : %%v

    where py >nul 2>nul
    if errorlevel 1 (
        where python >nul 2>nul
        if errorlevel 1 (
            echo [!time:~0,8!] Python was not found. Trying to install it with winget...
            where winget >nul 2>nul
            if errorlevel 1 (
                echo [!time:~0,8!] ERROR: winget is not available. Install Python 3 from https://python.org then run this again.
                pause
                exit /b 1
            )
            winget install -e --id Python.Python.3.13 --accept-package-agreements --accept-source-agreements
            echo [!time:~0,8!] Python installed. Close this window, open a NEW one and run this script again.
            pause
            exit /b 0
        )
        for /f "delims=" %%v in ('python --version') do echo [!time:~0,8!]   python : %%v
    ) else (
        for /f "delims=" %%v in ('py -3 --version') do echo [!time:~0,8!]   python : %%v via py launcher
    )

    echo.
    echo [!time:~0,8!] [2/6] Pulling latest main from GitHub
    pushd "%~dp0"
    echo [!time:~0,8!]   remote:
    git remote -v
    echo [!time:~0,8!]   fetching origin main
    git fetch origin main
    if errorlevel 1 (
        echo [!time:~0,8!] ERROR: git fetch failed. Check the network and git credentials.
        pause
        exit /b 1
    )
    echo [!time:~0,8!]   switching to main
    git checkout -f main
    if errorlevel 1 (
        echo [!time:~0,8!] ERROR: could not switch to main.
        pause
        exit /b 1
    )
    rem Make the VM match GitHub exactly. Untracked files such as .env and .venv are kept.
    echo [!time:~0,8!]   resetting working copy to origin/main
    git reset --hard origin/main
    if errorlevel 1 (
        echo [!time:~0,8!] ERROR: git reset failed.
        pause
        exit /b 1
    )
    echo [!time:~0,8!]   now at commit:
    git log -1 --oneline
    popd

    echo.
    echo [!time:~0,8!] [3/6] Verifying project files
    if not exist "%~dp0backend\automation\manage.py" (
        echo [!time:~0,8!] ERROR: Could not find "%~dp0backend\automation\manage.py"
        echo [!time:~0,8!] Contents of "%~dp0":
        dir /b "%~dp0"
        pause
        exit /b 1
    )
    echo [!time:~0,8!]   found manage.py
    if not exist "%~dp0UI\my-react-flow-app\dist\index.html" (
        echo [!time:~0,8!] ERROR: Prebuilt UI not found at "%~dp0UI\my-react-flow-app\dist\index.html"
        echo [!time:~0,8!] On your build machine run build-ui.bat, then: git add -f UI/my-react-flow-app/dist, commit and push.
        pause
        exit /b 1
    )
    echo [!time:~0,8!]   found prebuilt UI in dist

    echo.
    echo [!time:~0,8!] [4/6] Python virtual environment
    pushd "%~dp0backend\automation"
    if not exist ".venv\Scripts\python.exe" (
        echo [!time:~0,8!]   creating .venv
        where py >nul 2>nul
        if not errorlevel 1 (
            py -3 -m venv .venv
        ) else (
            python -m venv .venv
        )
        if errorlevel 1 (
            echo [!time:~0,8!] ERROR: Could not create the virtual environment.
            pause
            exit /b 1
        )
    ) else (
        echo [!time:~0,8!]   .venv already exists
    )

    call ".venv\Scripts\activate.bat"
    if errorlevel 1 (
        echo [!time:~0,8!] ERROR: Could not activate the virtual environment.
        pause
        exit /b 1
    )
    for /f "delims=" %%v in ('python --version') do echo [!time:~0,8!]   venv python: %%v

    echo [!time:~0,8!]   installing requirements.txt
    python -m pip install --upgrade pip
    python -m pip install -r requirements.txt
    if errorlevel 1 (
        echo [!time:~0,8!] ERROR: pip install failed.
        pause
        exit /b 1
    )

    echo.
    echo [!time:~0,8!] [5/6] Applying database migrations
    python manage.py migrate --noinput
    if errorlevel 1 (
        echo [!time:~0,8!] ERROR: migrate failed. Read the error above - often a missing .env or ODBC driver.
        pause
        exit /b 1
    )

    echo.
    echo [!time:~0,8!] [6/6] Starting servers - keep this window open
    echo [!time:~0,8!]   backend  http://localhost:8000
    echo [!time:~0,8!]   frontend http://localhost:8080
    python serve_all.py
    echo [!time:~0,8!] Server stopped with exit code !errorlevel!
    pause
    exit /b 0
)
