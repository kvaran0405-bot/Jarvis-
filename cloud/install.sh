#!/usr/bin/env bash
# Runs ON the cloud server (Ubuntu, e.g. Oracle Cloud's free tier): installs JARVIS as an always-on service.
# cloud-move.bat on the laptop runs it for you:  bash cloud/install.sh <satellite-token> [backup.zip]
set -e
cd "$(dirname "$0")/.."
TOKEN="$1"; ZIP="$2"
sudo apt-get update -qq
sudo apt-get install -y -qq python3-venv python3-pip ffmpeg >/dev/null
[ -d .venv ] || python3 -m venv .venv
. .venv/bin/activate
pip install -q -r requirements.txt
pip install -q -r requirements-extras.txt >/dev/null 2>&1 || true
sudo systemctl stop jarvis >/dev/null 2>&1 || true
# your memory, tasks, clients and settings from the laptop
if [ -n "$ZIP" ] && [ -f "$ZIP" ]; then python -m jarvis restore "$ZIP"; fi
touch .env
sed -i -E '/^(JARVIS_ROLE|JARVIS_SATELLITE_TOKEN|JARVIS_HOST)=/d' .env
{ echo "JARVIS_ROLE=cloud"; echo "JARVIS_HOST=127.0.0.1"; [ -n "$TOKEN" ] && echo "JARVIS_SATELLITE_TOKEN=$TOKEN"; } >> .env
sudo tee /etc/systemd/system/jarvis.service >/dev/null <<UNIT
[Unit]
Description=JARVIS (cloud)
After=network-online.target
[Service]
User=$USER
WorkingDirectory=$PWD
ExecStart=$PWD/.venv/bin/python -m jarvis serve
Restart=always
RestartSec=5
[Install]
WantedBy=multi-user.target
UNIT
sudo systemctl daemon-reload
sudo systemctl enable --now jarvis
# a private HTTPS address on your own Tailscale network: your phone and laptop reach it, nobody else can
sudo tailscale serve --bg 7334 >/dev/null 2>&1 || true
echo "JARVIS is running in the cloud."
