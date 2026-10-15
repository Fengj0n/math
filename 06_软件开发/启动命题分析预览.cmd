@echo off
chcp 65001 >nul
set "MATH2_HOME=%~dp0命题分析预览"
cd /d "%~dp0应用"
"%~dp0开发依赖\venv\Scripts\python.exe" "%~dp0应用\launcher.py"
