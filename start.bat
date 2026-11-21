@echo off
rem Group16 one-click start (Windows). Needs Python 3.11+ (https://www.python.org/downloads/).
rem Options are passed through, e.g.:  start.bat --port 9000   start.bat --minimal   start.bat --reset
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0"

set "PY="
for %%V in (3.14 3.13 3.12 3.11) do (
    if not defined PY (
        py -%%V -c "import sys" >nul 2>&1 && set "PY=py -%%V"
    )
)
if not defined PY (
    python -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>&1 && set "PY=python"
)
if not defined PY (
    echo [group16] Python 3.11 or newer was not found.
    echo [group16] Install it from https://www.python.org/downloads/ and tick "Add python.exe to PATH".
    goto :fail
)

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>&1 || (
        echo [group16] The existing .venv is broken or too old, recreating it...
        rmdir /s /q ".venv"
    )
)
if not exist ".venv\Scripts\python.exe" (
    echo [group16] Creating virtual environment with %PY% ...
    %PY% -m venv .venv || goto :fail
)

".venv\Scripts\python.exe" scripts\dev.py %*
if errorlevel 1 goto :fail
exit /b 0

:fail
echo.
echo [group16] Startup failed. See the messages above.
pause
exit /b 1
