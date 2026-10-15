@echo off
title Bokin Upscaler
cd /d "%~dp0"
set PYTHONUTF8=1
".venv\Scripts\python.exe" "bokin_launcher.py" %*
if errorlevel 1 pause
