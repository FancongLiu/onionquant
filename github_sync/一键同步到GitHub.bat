@echo off
chcp 65001 >nul
title 🔒 安全提交到 GitHub...
cls
echo ====================================
echo   🔒 安全提交代码到 GitHub
echo   （只提交非敏感文件，不会泄露个人信息）
echo ====================================
echo.

cd /d "e:\2026_AgentStudy\Python_code"

.venv\Scripts\python.exe scripts/auto_git_commit.py

echo.
echo ====================================
if %errorlevel% equ 0 (
    echo   ✅ 安全提交完成！
) else (
    echo   ❌ 提交时遇到问题，请看上面的提示
)
echo ====================================
echo.
pause
