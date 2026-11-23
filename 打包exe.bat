@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo 正在打包录音转写工作台桌面应用...
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --onefile --windowed --name "录音转写工作台" --icon "图标\图标.ico" --distpath "dist" --workpath "build" --specpath "." --paths "scripts" --hidden-import=webview.platforms.edgechromium --hidden-import=clr --hidden-import=pythonnet --collect-all webview "scripts\desktop_app.py"
if errorlevel 1 (
  echo 打包失败
  pause
) else (
  copy /Y "dist\录音转写工作台.exe" "录音转写工作台.exe" >nul
  echo 完成：录音转写工作台.exe 已生成在工作区根目录
  pause
)
