@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    python -m venv .venv
)

".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 exit /b %errorlevel%

".venv\Scripts\python.exe" mod_manager.py
