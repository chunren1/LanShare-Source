@echo off
chcp 65001 >nul
title LanShare 局域网文件共享工具
cd /d "%~dp0"

echo ============================================
echo   LanShare 局域网文件共享工具 - 一键启动
echo ============================================
echo.

rem ---------- 1. 检查 Python ----------
where python >nul 2>&1
if errorlevel 1 (
    echo [错误] 未检测到 Python，请先安装 Python 3.10+
    echo        下载地址: https://www.python.org/downloads/
    echo        安装时请勾选 "Add Python to PATH"
    pause
    exit /b 1
)

rem ---------- 2. 调用启动器（依赖检查/前端构建/启动均在其中） ----------
python start.py
if errorlevel 1 (
    echo.
    echo [提示] 启动失败，请查看上方错误信息后重试。
    pause
)
