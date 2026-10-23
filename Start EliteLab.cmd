@echo off
title EliteLab
cd /d "%~dp0"
rem Start the server first, give it a moment, then open the browser so the page does not load before the API is up.
start "EliteLab server" /min cmd /c "python -m elitelab serve & pause"
timeout /t 2 /nobreak >nul
start "" "http://localhost:8766/"
