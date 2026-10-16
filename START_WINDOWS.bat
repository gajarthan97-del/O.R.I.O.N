@echo off
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 (
  echo Please install Python 3.11 or later from https://python.org/downloads/
  pause
  exit /b 1
)
if not exist .venv (py -3 -m venv .venv)
call .venv\Scripts\activate.bat
python -m pip install -r requirements.txt
if errorlevel 1 (pause & exit /b 1)
if not exist .env (copy .env.example .env & echo Set your API keys in .env before using voice)
start "" http://127.0.0.1:8787
python run.py
pause
