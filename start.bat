@echo off
REM One-command launcher for Windows: creates a venv, installs deps, starts JARVIS OS
cd /d %~dp0
if not exist .venv python -m venv .venv
call .venv\Scripts\activate.bat
pip install -q -r requirements.txt
if not exist .env (copy .env.example .env >nul & echo Created .env - add your ANTHROPIC_API_KEY to it.)
if not exist profile.md copy profile.example.md profile.md >nul
python -m jarvis serve --open
