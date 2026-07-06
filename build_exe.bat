@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    python -m venv .venv
)

".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 exit /b %errorlevel%

".venv\Scripts\python.exe" -m pip install -r requirements-dev.txt
if errorlevel 1 exit /b %errorlevel%

".venv\Scripts\pyinstaller.exe" ^
    --noconfirm ^
    --clean ^
    --onefile ^
    --windowed ^
    --name "Looseleaf Mod Manager" ^
    --collect-data tkinterdnd2 ^
    mod_manager.py

if errorlevel 1 exit /b %errorlevel%

echo.
echo Built: dist\Looseleaf Mod Manager.exe
