@echo off
setlocal
title EliteLab
cd /d "%~dp0"
if exist "runtime\python.exe" (
    "runtime\python.exe" -m elitelab serve --open-browser %*
    goto finished
)
python -c "import sys; sys.exit(sys.version_info < (3, 10))" >nul 2>&1
if not errorlevel 1 (
    python -m elitelab serve --open-browser %*
    goto finished
)
py -3 -c "import sys; sys.exit(sys.version_info < (3, 10))" >nul 2>&1
if not errorlevel 1 (
    py -3 -m elitelab serve --open-browser %*
    goto finished
)
echo Python 3.10 or newer was not found.
echo Download the EliteLab Windows bundle with Python included, then extract it fully.
echo The GitHub source ZIP requires Python to be installed separately.
pause
exit /b 1

:finished
if errorlevel 1 (
    echo.
    echo EliteLab could not start. The error is shown above.
    pause
    exit /b 1
)
