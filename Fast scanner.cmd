@echo off
cd /d "%~dp0"
if "%~1"=="" (
    powershell -NoExit -NoProfile -ExecutionPolicy Bypass -File "%~dp0fast_scanner_shell.ps1"
) else (
    ".venv\Scripts\python.exe" -m scanner.buscar %*
)
