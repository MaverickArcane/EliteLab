@echo off
setlocal
rem Restart loop: exit status 75 means "restart me" (Settings saved); anything else, 76 and up included, ends it.
rem Only the first run opens the browser; a restart keeps the tab the setup page is already waiting in.
cd /d "%~dp0.."
set "lab_open=--open-browser"
:again
python -m elitelab %lab_open% %*
set "lab_status=%errorlevel%"
set "lab_open="
if %lab_status% GEQ 76 goto done
if %lab_status% EQU 75 goto again
:done
exit /b %lab_status%
