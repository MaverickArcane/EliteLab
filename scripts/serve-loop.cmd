@echo off
cd /d "%~dp0.."
:again
python -m elitelab serve
if errorlevel 76 goto done
if errorlevel 75 goto again
:done
pause
