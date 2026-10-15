@echo off
rem Double-click to install Bokin Upscaler (no administrator rights needed).
chcp 65001 >nul
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup.ps1" -PauseOnError %*
if errorlevel 1 exit /b 1
echo.
pause
