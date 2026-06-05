@echo off
chcp 65001 >nul
title C盘紧急清理 — 腾出空间
echo =============================================
echo   C盘紧急清理脚本
echo   目标: 腾出约 30 GB 空间
echo =============================================
echo.

echo 第一步: 清空回收站
rd /s /q C:\$Recycle.bin 2>nul
powershell -Command "Clear-RecycleBin -Force -ErrorAction SilentlyContinue" >nul 2>&1
echo    ✓ 回收站已清空
echo.

echo 第二步: 删除无用软件数据
set "FOLDERS_TO_DELETE=C:\Users\28462\AppData\Local\JianyingPro C:\Users\28462\AppData\Roaming\webcast_mate C:\Users\28462\AppData\Local\sogoupdf C:\Users\28462\AppData\Roaming\KuGou8 C:\Users\28462\AppData\Local\Temp C:\Users\28462\AppData\Local\pip C:\Users\28462\AppData\Local\CrashDumps C:\Users\28462\AppData\Local\qq-chat-updater C:\Users\28462\AppData\Local\app_shell_cache_2079"
for %%d in (%FOLDERS_TO_DELETE%) do (
    if exist "%%d" (
        echo    删除: %%~nd...
        takeown /F "%%d" /R /D Y >nul 2>&1
        icacls "%%d" /grant "28462:F" /T /Q >nul 2>&1
        rmdir /s /q "%%d" 2>nul
        if exist "%%d" ( echo    ✗ %%~nd 删除失败 ) else ( echo    ✓ %%~nd 已删除 )
    ) else (
        echo    - %%~nd 已不存在
    )
)
echo.

echo 第三步: 迁移 WeChat Files (13.4 GB) 到 E:\
if exist "E:\OnionQuant_Data\WeChat Files" (
    if exist "C:\Users\28462\Documents\WeChat Files" (
        echo    删除C盘原始文件...
        takeown /F "C:\Users\28462\Documents\WeChat Files" /R /D Y >nul 2>&1
        rmdir /s /q "C:\Users\28462\Documents\WeChat Files" 2>nul
        if exist "C:\Users\28462\Documents\WeChat Files" (
            echo    ✗ 删除失败，请手动关闭微信/QQ后重试
        ) else (
            mklink /J "C:\Users\28462\Documents\WeChat Files" "E:\OnionQuant_Data\WeChat Files"
            echo    ✓ WeChat Files 已迁移到E盘！
        )
    ) else (
        mklink /J "C:\Users\28462\Documents\WeChat Files" "E:\OnionQuant_Data\WeChat Files" 2>nul
        echo    ✓ WeChat Files 链接已创建
    )
) else (
    echo    ✗ E:\OnionQuant_Data\WeChat Files 不存在！
)
echo.

echo 第四步: 迁移 WPS kingsoft (3.7 GB) 到 E:\
if exist "E:\OnionQuant_Data\kingsoft" (
    if exist "C:\Users\28462\AppData\Roaming\kingsoft" (
        echo    删除C盘原始文件（请先关闭WPS）...
        takeown /F "C:\Users\28462\AppData\Roaming\kingsoft" /R /D Y >nul 2>&1
        rmdir /s /q "C:\Users\28462\AppData\Roaming\kingsoft" 2>nul
        if exist "C:\Users\28462\AppData\Roaming\kingsoft" (
            echo    ✗ 删除失败！请关闭WPS所有进程后重新运行本脚本
        ) else (
            mklink /J "C:\Users\28462\AppData\Roaming\kingsoft" "E:\OnionQuant_Data\kingsoft"
            echo    ✓ kingsoft 已迁移到E盘！
        )
    ) else (
        mklink /J "C:\Users\28462\AppData\Roaming\kingsoft" "E:\OnionQuant_Data\kingsoft" 2>nul
        echo    ✓ kingsoft 链接已创建
    )
) else (
    echo    ✗ E:\OnionQuant_Data\kingsoft 不存在！
)
echo.
echo =============================================
echo   执行完毕！
echo   关闭此窗口前请查看上方是否有✗失败项
echo =============================================
pause
