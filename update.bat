@echo off
REM Updates JARVIS to the newest version from GitHub and restarts it.
REM Your settings (.env), profile, memory (data) and installed parts (.venv) are never touched.
cd /d %~dp0
set "REPO=https://github.com/kvaran0405-bot/Jarvis-.git"
set "BRANCH=ccr-b1820a97-njfthb"

where git >nul 2>nul
if errorlevel 1 (
  echo Installing Git - one time only...
  winget install --id Git.Git -e --silent --accept-package-agreements --accept-source-agreements
  set "PATH=%PATH%;%ProgramFiles%\Git\cmd"
)
where git >nul 2>nul
if errorlevel 1 (
  echo.
  echo  Git could not be installed automatically. Install it from https://git-scm.com - click Next on everything - then run update again.
  pause
  exit /b 1
)

if not exist .git (
  git init -q
  git remote add origin %REPO%
)
echo Downloading the newest JARVIS... - the first time, a browser may ask you to sign in to GitHub
git fetch -q origin %BRANCH%
if errorlevel 1 (
  echo.
  echo  Could not download from GitHub. If a sign-in window appeared, finish signing in and run update again.
  pause
  exit /b 1
)
git reset -q --hard FETCH_HEAD
echo Updated to:
git log -1 --format="   %%s  [%%cr]"

REM Stop the running JARVIS and its helpers, then start the new version.
if exist data\jarvis.pid (
  for /f %%p in (data\jarvis.pid) do taskkill /pid %%p /t /f >nul 2>nul
)
timeout /t 2 /nobreak >nul
start "JARVIS" cmd /c "%~dp0start.bat"
echo.
echo  JARVIS is restarting with the new version. You can close this window.
timeout /t 5 >nul
