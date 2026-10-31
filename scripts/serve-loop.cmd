@echo off
cd /d "%~dp0.."
:again
python -m elitelab --open-browser %*
set "lab_status=%errorlevel%"
if "%lab_status%"=="75" goto again
exit /b %lab_status%
