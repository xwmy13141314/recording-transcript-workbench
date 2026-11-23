@echo off
chcp 65001 >nul
cd /d "%~dp0"
if exist "录音转写工作台.exe" (
  start "" "录音转写工作台.exe"
) else (
  echo 未找到 录音转写工作台.exe，请先运行 打包exe.bat
  pause
)
