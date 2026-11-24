@echo off
REM Moves JARVIS's always-on brain to your free cloud server, and makes this laptop its "satellite".
REM Run it after following docs/CLOUD.md (Oracle sign-up + Tailscale on the server). Safe to run again.
cd /d %~dp0
call .venv\Scripts\activate.bat
set /p CLOUD=Your cloud server's Tailscale name (e.g. jarvis-cloud):
if "%CLOUD%"=="" exit /b 1
echo.
echo [1/5] Backing up your memory, tasks, clients and settings...
for /f "delims=" %%z in ('python -c "from jarvis.studio import backup;print(backup(True))"') do set ZIP=%%z
echo [2/5] Packing JARVIS...
tar -czf "%TEMP%\jarvis.tgz" --exclude=.venv --exclude=data --exclude=.git --exclude=bridge/node_modules .
echo [3/5] Copying to %CLOUD% over Tailscale...
scp "%TEMP%\jarvis.tgz" "%ZIP%" ubuntu@%CLOUD%:~/ || (echo Couldn't reach %CLOUD%. Is Tailscale on here and on the server? & pause & exit /b 1)
for /f %%t in ('python -c "import secrets;print(secrets.token_hex(24))"') do set SAT=%%t
for /f %%n in ('python -c "import os;print(os.path.basename(r'%ZIP%'))"') do set ZIPNAME=%%n
echo [4/5] Installing on the server (a few minutes the first time)...
ssh ubuntu@%CLOUD% "mkdir -p ~/jarvis && tar -xzf ~/jarvis.tgz -C ~/jarvis && bash ~/jarvis/cloud/install.sh %SAT% ~/%ZIPNAME%"
for /f "delims=" %%u in ('ssh ubuntu@%CLOUD% "tailscale status --json" ^| python -c "import sys,json;print('https://'+json.load(sys.stdin)['Self']['DNSName'].rstrip('.'))"') do set URL=%%u
echo [5/5] Making this laptop the satellite and pointing your phone at the cloud...
python -c "import re,pathlib;p=pathlib.Path('.env');s=p.read_text() if p.exists() else '';s=re.sub(r'(?m)^(JARVIS_ROLE|JARVIS_CLOUD_URL|JARVIS_SATELLITE_TOKEN)=.*\n?','',s);p.write_text(s.rstrip()+'\nJARVIS_ROLE=satellite\nJARVIS_CLOUD_URL=%URL%\nJARVIS_SATELLITE_TOKEN=%SAT%\n')"
python -c "import urllib.request,json;urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:7334/api/cloud/moved',data=json.dumps({'url':'%URL%'}).encode(),headers={'Content-Type':'application/json'}),timeout=10)" 2>nul
echo.
echo  Done. JARVIS now lives at %URL% (24/7). Restart JARVIS on this laptop (start.bat) to link it as the satellite.
pause
