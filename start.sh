#!/usr/bin/env bash
# One-command launcher: sets everything up and starts JARVIS OS on http://127.0.0.1:7334
set -e
cd "$(dirname "$0")"
[ -d .venv ] || python3 -m venv .venv
. .venv/bin/activate
pip install -q -r requirements.txt
[ -f .env ] || { cp .env.example .env; echo "Created .env - add your ANTHROPIC_API_KEY to it."; }
[ -f profile.md ] || cp profile.example.md profile.md
grep -q '^JARVIS_BRIDGE_TOKEN=..' .env || echo "JARVIS_BRIDGE_TOKEN=$(python -c 'import secrets;print(secrets.token_hex(16))')" >> .env

if grep -qi '^JARVIS_WHATSAPP=on' .env; then
  if command -v node >/dev/null; then
    (cd bridge && [ -d node_modules ] || npm install --silent)
    echo "Starting WhatsApp bridge (scan the QR code the first time)..."
    node bridge/whatsapp-bridge.js &
    BRIDGE=$!
    trap 'kill $BRIDGE 2>/dev/null' EXIT
  else
    echo "WhatsApp is on but Node.js is missing - install it from https://nodejs.org"
  fi
fi
python -m jarvis serve --open
