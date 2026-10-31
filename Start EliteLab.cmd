@echo off
title EliteLab
cd /d "%~dp0"
rem The server opens its actual configured URL after binding successfully.
start "EliteLab server" /min cmd /c ""%~dp0scripts\serve-loop.cmd" %* & pause"
