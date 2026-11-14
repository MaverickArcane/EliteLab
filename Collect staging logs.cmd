@echo off
setlocal
cd /d "%~dp0"
if exist "runtime\python.exe" (
  "runtime\python.exe" -m elitelab.staging collect --prompt
) else (
  python -m elitelab.staging collect --prompt
)
pause
