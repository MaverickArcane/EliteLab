@echo off
setlocal
cd /d "%~dp0"
if exist "runtime\python.exe" (
  "runtime\python.exe" -m elitelab.staging run
) else (
  python -m elitelab.staging run
)
pause
