#!/usr/bin/env bash
# One-command launcher: creates a venv, installs deps, starts JARVIS OS on http://127.0.0.1:7334
set -e
cd "$(dirname "$0")"
[ -d .venv ] || python3 -m venv .venv
. .venv/bin/activate
pip install -q -r requirements.txt
[ -f .env ] || { cp .env.example .env; echo "Created .env - add your ANTHROPIC_API_KEY to it."; }
[ -f profile.md ] || cp profile.example.md profile.md
exec python -m jarvis serve --open
