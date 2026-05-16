@echo off
chcp 65001 >nul
title 🔄 正在同步代码到 GitHub...
cls
echo ====================================
echo   🔄 正在同步代码到 GitHub...
echo ====================================
echo.

cd /d "%~dp0"

python scripts/auto_git_sync.py

echo.
echo ====================================
if %errorlevel% equ 0 (
    echo   ✅ 同步完成！
) else (
    echo   ❌ 同步时遇到问题，请看上面的提示
)
echo ====================================
echo.
pause
