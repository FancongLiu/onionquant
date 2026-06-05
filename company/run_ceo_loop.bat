@echo off
chcp 65001 >nul
title OnionQuant — 24/7 CEO Agent 启动脚本

echo ========================================
echo    🧅 OnionQuant 24/7 持久化执行系统
echo ========================================
echo.
echo 本脚本负责：
echo   1. 启动 Dashboard Server (端口 8765)
echo   2. 确保 Claude Code 持久化 cron 就位
echo ========================================
echo.

cd /d "%~dp0.."

REM ── Python 环境检查 ──
if not exist ".venv\Scripts\python.exe" (
    echo ❌ 未找到 .venv 虚拟环境，请先创建
    pause
    exit /b 1
)

REM ── 依赖安装 ──
echo 🔧 安装/更新依赖...
.venv\Scripts\pip install -q -r company/requirements.txt 2>&1
if %errorlevel% neq 0 (
    echo ⚠️  依赖安装警告（继续运行）
)

REM ── 杀掉旧服务器进程 ──
echo 🔍 检查并清理旧进程...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8765" ^| findstr "LISTENING" 2^>nul') do (
    echo   → 关闭旧进程 PID:%%a
    taskkill //F //PID %%a 2>nul
)
timeout /t 2 /nobreak >nul

REM ── 启动服务器 ──
echo 🚀 启动 Dashboard Server...
start "OnionQuant-Server" /MIN .venv\Scripts\python onionquant/server.py

REM ── 等待服务器就绪 ──
echo ⏳ 等待服务器就绪...
:wait_server
timeout /t 2 /nobreak >nul
curl -s http://localhost:8765/api/status >nul 2>&1
if %errorlevel% neq 0 (
    goto wait_server
)
echo ✅ 服务器已就绪: http://localhost:8765

REM ── 打开浏览器 ──
start http://localhost:8765

REM ── 指令 ──
echo.
echo ========================================
echo    ✅ 服务器运行中 (后台窗口)
echo    🌐 http://localhost:8765
echo ========================================
echo.
echo    📌 要让 Agent 24/7 运行，还需要：
echo.
echo    1. 打开 VS Code
echo    2. 按 Ctrl+Shift+P → 输入 "Claude Code: Open"
echo    3. 在 Claude Code 面板中输入:
echo       /run company\CHAIRMAN_PROMPT.md
echo    4. Agent 启动后会自动创建持久化 cron
echo    5. 保持 VS Code 开着，不要关
echo.
echo    ⚡ 关键设置：
echo    - Windows 电源选项 → 从不睡眠
echo    - 合上笔记本盖子 → 不执行任何操作
echo    - 关闭显示器 → 可以（不影响运行）
echo.
echo ========================================
echo    🔴 按任意键停止服务器并退出
echo ========================================
pause >nul

REM ── 清理 ──
echo 🛑 正在停止服务器...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8765" ^| findstr "LISTENING" 2^>nul') do (
    taskkill //F //PID %%a 2>nul
)
echo ✅ 已停止
