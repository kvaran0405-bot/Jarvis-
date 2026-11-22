#!/usr/bin/env bash
# Updates JARVIS to the newest version from GitHub and restarts it (settings, profile and data are kept).
set -e
cd "$(dirname "$0")"
REPO="https://github.com/kvaran0405-bot/Jarvis-.git"
BRANCH="ccr-b1820a97-njfthb"
[ -d .git ] || { git init -q; git remote add origin "$REPO"; }
git fetch -q origin "$BRANCH"
git reset -q --hard FETCH_HEAD
echo "Updated to: $(git log -1 --format='%s (%cr)')"
[ -f data/jarvis.pid ] && kill "$(cat data/jarvis.pid)" 2>/dev/null || true
sleep 2
nohup ./start.sh >/dev/null 2>&1 &
echo "JARVIS is restarting."
