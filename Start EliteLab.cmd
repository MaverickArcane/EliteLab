@echo off
title EliteLab
cd /d "%~dp0"
rem Start the server first, give it a moment, then open the browser so the page does not load before the API is up.
rem Relative path on purpose: cmd /c strips quotes around a path with parentheses; we are already in this folder.
start "EliteLab server" /min cmd /c scripts\serve-loop.cmd
timeout /t 2 /nobreak >nul
start "" "http://localhost:8766/"
