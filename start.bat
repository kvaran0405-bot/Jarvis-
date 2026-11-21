@echo off
REM One-command launcher for Windows: sets everything up and starts JARVIS OS
cd /d %~dp0
if not exist .venv python -m venv .venv
call .venv\Scripts\activate.bat
pip install -q -r requirements.txt
if not exist .env (copy .env.example .env >nul & echo Created .env - add your ANTHROPIC_API_KEY to it.)
if not exist profile.md copy profile.example.md profile.md >nul
findstr /r /c:"^JARVIS_BRIDGE_TOKEN=.." .env >nul || (for /f %%t in ('python -c "import secrets;print(secrets.token_hex(16))"') do echo JARVIS_BRIDGE_TOKEN=%%t>> .env)

findstr /i /c:"JARVIS_WHATSAPP=on" .env >nul && (
  where node >nul 2>nul && (
    if not exist bridge\node_modules (pushd bridge & call npm install --silent & popd)
    echo Starting WhatsApp bridge in a new window - scan the QR code the first time.
    start "JARVIS WhatsApp" cmd /k node bridge\whatsapp-bridge.js
  ) || echo WhatsApp is on but Node.js is missing - install it from https://nodejs.org
)
python -m jarvis serve --open
