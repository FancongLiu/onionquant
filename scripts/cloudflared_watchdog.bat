@echo off
REM Cloudflared Watchdog — keeps onionoffice.xyz alive
REM http2 protocol (TCP-based, stable through VPN — NOT quic/UDP)
REM If tunnel dies, auto-restart within 30 seconds

:loop
tasklist /FI "IMAGENAME eq cloudflared.exe" 2>NUL | find /I "cloudflared.exe" >NUL
if %ERRORLEVEL% NEQ 0 (
    echo [%date% %time%] Tunnel DOWN — restarting named tunnel...
    C:\Users\28462\cloudflared.exe tunnel --protocol http2 --no-autoupdate run 52625950-1312-48b9-926f-52b6424482ed >> C:\Users\28462\.cloudflared\tunnel.log 2>> C:\Users\28462\.cloudflared\tunnel_error.log
    echo [%date% %time%] Tunnel restarted with exit code %ERRORLEVEL%
)
timeout /t 1800 /nobreak >NUL
goto loop
