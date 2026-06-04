@echo off
chcp 65001 >nul
title OnionQuant — 开机自启
cd /d "%~dp0.."

echo ========================================
echo    OnionQuant 开机自启
echo    %date% %time%
echo ========================================

REM ── 1. 清理旧进程 ──
echo [1/5] 清理旧进程...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8765" ^| findstr "LISTENING" 2^>nul') do (
    taskkill //F //PID %%a 2>nul
)

REM ── 2. Dashboard Server ──
echo [2/5] Dashboard Server (port 8765)...
start "OnionQuant-Server" /MIN .venv\Scripts\python company\server.py

REM wait for server to be ready
timeout /t 3 >nul

REM ── 3. Tunnel (cloudflared + auto URL notify) ──
echo [3/5] Tunnel (cloudflared + auto URL push)...
start "Tunnel-Sync" /MIN .venv\Scripts\python scripts\tunnel_sync.py

REM ── 4. Background Scheduler (cron tasks + WeChat push) ──
echo [4/5] Background Scheduler...
start "BgScheduler" /MIN .venv\Scripts\python scripts\background_scheduler.py

REM ── 5. VS Code ──
echo [5/5] VS Code...
start "" "C:\Users\28462\AppData\Local\Programs\Microsoft VS Code\Code.exe" "e:\2026_AgentStudy\Python_code"

echo.
echo    All services started
echo    Dashboard: tunnel URL in context_state.json
echo    Local: http://localhost:8765
echo.
