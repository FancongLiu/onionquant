@echo off
rem Move Codex installer to E:\Codex_Project
set "SRC=C:\Users\28462\Downloads\Codex Installer.exe"
set "DST_FOLDER=E:\Codex_Project"

if not exist "%DST_FOLDER%" (
  mkdir "%DST_FOLDER%"
  echo Created folder: %DST_FOLDER%
)

if exist "%SRC%" (
  move /Y "%SRC%" "%DST_FOLDER%\" >nul
  echo Moved "%SRC%" to "%DST_FOLDER%"
) else (
  echo Source not found: "%SRC%"
  pause
  exit /b 1
)
echo.
echo Contents of "%DST_FOLDER%":

dir "%DST_FOLDER%"
pause
