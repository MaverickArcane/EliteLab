@echo off
setlocal
rem Use the same interpreter checks, instance guard and restart loop as normal startup.
call "%~dp0Start EliteLab.cmd" --setup %*
exit /b %errorlevel%
