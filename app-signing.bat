@echo off
rem One-time: gives the JARVIS phone app a permanent key so it can update itself. Double-click me.
cd /d "%~dp0"
if exist .venv\Scripts\python.exe (set PY=.venv\Scripts\python.exe) else (set PY=python)
%PY% -m jarvis signing-key
pause
