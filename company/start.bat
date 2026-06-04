@echo off
chcp 65001 >nul
title OnionQuant — Chairman Dashboard Server

echo ========================================
echo    🧅 OnionQuant Dashboard Server
echo ========================================
echo.

cd /d "%~dp0.."

if not exist ".venv\Scripts\python.exe" (
    echo ❌ 未找到 .venv 虚拟环境
    pause
    exit /b 1
)

echo 🔧 安装/更新依赖...
.venv\Scripts\pip install -q -r company/requirements.txt

echo.
echo 🚀 启动服务器...
echo    浏览器打开: http://localhost:8765
echo    按 Ctrl+C 停止
echo.

.venv\Scripts\python company/server.py

pause
