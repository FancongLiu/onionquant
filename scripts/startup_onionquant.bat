@echo off
REM OnionQuant Auto-Startup Script - runs on user login via Registry Run key
set ROOT=e:\2026_AgentStudy\Python_code
set LOG=%ROOT%\logs\startup.log

if not exist "%ROOT%\logs" mkdir "%ROOT%\logs"

echo [%date% %time%] OnionQuant startup initiated >> %LOG%

REM Wait for network
timeout /t 30 /nobreak > nul

REM Start cloudflared tunnel if not running
tasklist /FI "IMAGENAME eq cloudflared.exe" 2>nul | find /I /N "cloudflared.exe" >nul
if %ERRORLEVEL% NEQ 0 (
    echo [%date% %time%] Starting cloudflared... >> %LOG%
    start "" "C:\Users\28462\AppData\Local\Microsoft\WinGet\Packages\Cloudflare.cloudflared_Microsoft.Winget.Source_8wekyb3d8bbwe\cloudflared.exe" tunnel run onion-tunnel >> %ROOT%\logs\cloudflared.log 2>&1
)

REM Start backend idempotently
echo [%date% %time%] Starting backend... >> %LOG%
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%ROOT%\scripts\start_onionquant.ps1" -Restart >> %ROOT%\logs\startup_backend.log 2>&1

echo [%date% %time%] OnionQuant startup complete >> %LOG%
