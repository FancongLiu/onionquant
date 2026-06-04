@echo off
REM OnionQuant Auto-Startup Script — runs on user login via Registry Run key
set ROOT=e:\2026_AgentStudy\Python_code
set VENV=%ROOT%\.venv\Scripts\python.exe
set LOG=%ROOT%\logs\startup.log

if not exist "%ROOT%\logs" mkdir "%ROOT%\logs"

echo [%date% %time%] OnionQuant startup initiated >> %LOG%

REM Wait for network
timeout /t 30 /nobreak > /dev/null

REM Start cloudflared tunnel if not running
tasklist /FI "IMAGENAME eq cloudflared.exe" 2>/dev/null | find /I /N "cloudflared.exe" >/dev/null
if %ERRORLEVEL% NEQ 0 (
    echo [%date% %time%] Starting cloudflared... >> %LOG%
    start "" "C:\Users\28462\AppData\Local\Microsoft\WinGet\Packages\Cloudflare.cloudflared_Microsoft.Winget.Source_8wekyb3d8bbwe\cloudflared.exe" tunnel run onion-tunnel >> %ROOT%\logs\cloudflared.log 2>&1
)

REM Start company server
echo [%date% %time%] Starting server... >> %LOG%
start /B "" "%VENV%" "%ROOT%\company\server.py" >> %ROOT%\logs\server.log 2>&1

REM Start background scheduler
echo [%date% %time%] Starting scheduler... >> %LOG%
start /B "" "%VENV%" "%ROOT%\scripts\background_scheduler.py" >> %ROOT%\logs\background_scheduler.log 2>&1

echo [%date% %time%] OnionQuant startup complete >> %LOG%
