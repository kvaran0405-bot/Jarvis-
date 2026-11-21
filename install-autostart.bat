@echo off
REM Makes JARVIS start by itself every time you log in to Windows.
REM To undo: press Win+R, type  shell:startup  , and delete "JARVIS.bat".
set STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup
(
  echo @echo off
  echo cd /d "%~dp0"
  echo start "JARVIS" /min cmd /c "%~dp0start.bat"
) > "%STARTUP%\JARVIS.bat"
echo Done. JARVIS will start automatically when you log in.
pause
