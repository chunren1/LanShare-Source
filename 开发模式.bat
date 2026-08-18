@echo off
chcp 65001 >nul
title LanShare 开发模式启动器
cd /d "%~dp0"

echo ============================================
echo   LanShare 开发模式（前后端热重载）
echo ============================================
echo.

rem ---------- 1. 检查 Python ----------
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未检测到 Python，请先安装 Python 3.10+
    pause
    exit /b 1
)

rem ---------- 2. 检查 Node.js ----------
node --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未检测到 Node.js，请先安装 Node.js 18+
    echo        下载地址: https://nodejs.org/
    pause
    exit /b 1
)

rem ---------- 3. 安装依赖 ----------
python -c "import fastapi, uvicorn, multipart" >nul 2>&1
if errorlevel 1 (
    echo [首次运行] 正在安装后端依赖...
    python -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
)

if not exist "frontend\node_modules" (
    echo [首次运行] 正在安装前端依赖...
    cd frontend
    call npm install --registry=https://registry.npmmirror.com
    cd ..
)

rem ---------- 4. 启动 ----------
echo.
echo [启动] 请保持本窗口运行后端 (8000)，再双击 "启动.bat" 或另开终端运行:
echo        cd frontend ^&^& npm run dev    -- 前端开发地址: http://localhost:5173
echo.
echo [提示] 后端正在启动...
python -m app.main
pause
