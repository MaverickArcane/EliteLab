@echo off
title EliteLab
cd /d "%~dp0"
start "" "http://localhost:8766/"
python -m elitelab
pause
