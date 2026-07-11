@echo off
setlocal
cd /d "%~dp0"

rem Install dependencies only when the venv is first created; running pip on
rem every launch added seconds to startup.
if not exist ".venv\Scripts\python.exe" (
    python -m venv .venv
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
    if errorlevel 1 exit /b %errorlevel%
)

".venv\Scripts\python.exe" mi_studio.py
