@echo off
setlocal

set "BACKEND_DIR=%~dp0backend\automation"
if not exist "%BACKEND_DIR%\manage.py" (
    echo ERROR: Could not find backend\automation\manage.py.
    exit /b 1
)

pushd "%BACKEND_DIR%"
if errorlevel 1 (
    echo ERROR: Could not enter "%BACKEND_DIR%".
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    where py >nul 2>nul
    if not errorlevel 1 (
        py -3 -m venv .venv
    ) else (
        where python >nul 2>nul
        if errorlevel 1 (
            echo ERROR: Python was not found. Install Python and add it to PATH.
            popd
            exit /b 1
        )
        python -m venv .venv
    )
    if errorlevel 1 (
        echo ERROR: Could not create the Python virtual environment.
        popd
        exit /b 1
    )
)

call ".venv\Scripts\activate.bat"
if errorlevel 1 (
    echo ERROR: Could not activate the Python virtual environment.
    popd
    exit /b 1
)

python -m pip install --upgrade pip
if errorlevel 1 goto failed

python -m pip install -r requirements.txt
if errorlevel 1 goto failed

python manage.py migrate
if errorlevel 1 goto failed

if not defined DJANGO_HOST set "DJANGO_HOST=0.0.0.0"
if not defined DJANGO_PORT set "DJANGO_PORT=8000"

echo Starting Django at http://%DJANGO_HOST%:%DJANGO_PORT%/
python manage.py runserver %DJANGO_HOST%:%DJANGO_PORT%
set "SERVER_EXIT_CODE=%ERRORLEVEL%"
popd
exit /b %SERVER_EXIT_CODE%

:failed
set "COMMAND_EXIT_CODE=%ERRORLEVEL%"
popd
echo ERROR: Backend setup failed with exit code %COMMAND_EXIT_CODE%.
exit /b %COMMAND_EXIT_CODE%