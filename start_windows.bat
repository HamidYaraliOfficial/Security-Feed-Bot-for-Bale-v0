@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "PY="
py -3 --version >nul 2>nul && set "PY=py -3"
if not defined PY (
  python --version >nul 2>nul && set "PY=python"
)
if not defined PY (
  echo Python 3 is not installed. Download it from https://www.python.org/downloads/
  echo During setup, tick "Add python.exe to PATH". Then run this file again.
  pause
  exit /b 1
)
if not exist ".venv\Scripts\python.exe" (
  echo Creating virtual environment...
  %PY% -m venv .venv
)
echo Installing requirements (first run only)...
".venv\Scripts\python.exe" -m pip install -r requirements.txt -q
".venv\Scripts\python.exe" run.py
pause
