@echo off
title EliteLab
cd /d "%~dp0"
rem The server opens the dashboard itself once it is listening, on the host and port it really bound.
rem Relative path on purpose: cmd /c strips quotes around a path with parentheses; we are already in this folder.
rem The quotes keep "& pause" inside the server window, so a startup error stays readable.
start "EliteLab server" /min cmd /c "scripts\serve-loop.cmd %* & pause"
