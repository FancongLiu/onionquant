@echo off
chcp 65001 >nul
echo ============================================
echo   C盘 → E盘 数据迁移
echo   微信文件 + WPS数据
echo ============================================
echo.

echo [1/2] 处理 WeChat Files (13.4 GB)...
if exist "E:\OnionQuant_Data\WeChat Files" (
    echo    ✓ E盘目标存在
    if exist "C:\Users\28462\Documents\WeChat Files" (
        echo    删除C盘原文件...
        takeown /F "C:\Users\28462\Documents\WeChat Files" /R /D Y >nul 2>&1
        rmdir /s /q "C:\Users\28462\Documents\WeChat Files" 2>nul
        if exist "C:\Users\28462\Documents\WeChat Files" (
            echo    ⚠ 删除失败！请关闭微信/资源管理器后重试
        ) else (
            mklink /J "C:\Users\28462\Documents\WeChat Files" "E:\OnionQuant_Data\WeChat Files"
            echo    ✓ WeChat Files 完成！
        )
    ) else (
        mklink /J "C:\Users\28462\Documents\WeChat Files" "E:\OnionQuant_Data\WeChat Files"
        echo    ✓ 链接已创建！
    )
) else (
    echo    ✗ E盘目标不存在
)
echo.

echo [2/2] 处理 WPS kingsoft (3.7 GB)...
if exist "E:\OnionQuant_Data\kingsoft" (
    echo    ✓ E盘目标存在
    if exist "C:\Users\28462\AppData\Roaming\kingsoft" (
        echo    删除C盘原文件...
        rmdir /s /q "C:\Users\28462\AppData\Roaming\kingsoft" 2>nul
        if exist "C:\Users\28462\AppData\Roaming\kingsoft" (
            echo    ⚠ 删除失败！请关闭WPS后重试
        ) else (
            mklink /J "C:\Users\28462\AppData\Roaming\kingsoft" "E:\OnionQuant_Data\kingsoft"
            echo    ✓ kingsoft 完成！
        )
    ) else (
        mklink /J "C:\Users\28462\AppData\Roaming\kingsoft" "E:\OnionQuant_Data\kingsoft"
        echo    ✓ 链接已创建！
    )
) else (
    echo    ✗ E盘目标不存在
)
echo.
echo ============================================
echo   完成！C盘应腾出约 17 GB
echo ============================================
pause
