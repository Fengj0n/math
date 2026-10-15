@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist "..\开发依赖\pdf-import-venv\Scripts\pythonw.exe" (
  echo 本地识别环境尚未安装，请查看 pdf_import\README.md。
  pause
  exit /b 1
)
start "" "..\开发依赖\pdf-import-venv\Scripts\pythonw.exe" -m pdf_import --open
