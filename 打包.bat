@echo off
chcp 936 >nul
title LanShare 打包工具
cd /d "%~dp0"

echo ====================================
echo   LanShare 一键打包（PyInstaller）
echo ====================================
echo.

REM 检查 Python
where python >nul 2>nul
if errorlevel 1 (
    echo [错误] 未检测到 Python，请先安装 Python 3.10+ 并勾选 "Add to PATH"
    pause
    exit /b 1
)

REM 检查 / 安装 PyInstaller
python -c "import PyInstaller" >nul 2>nul
if errorlevel 1 (
    echo [信息] 正在安装 PyInstaller ...
    python -m pip install pyinstaller -i https://pypi.tuna.tsinghua.edu.cn/simple
    if errorlevel 1 (
        echo [错误] PyInstaller 安装失败
        pause
        exit /b 1
    )
)

REM 前端产物缺失时自动构建；带参数 rebuild 则强制重新构建
set NEED_BUILD=0
if not exist "frontend\dist\index.html" set NEED_BUILD=1
if /i "%1"=="rebuild" set NEED_BUILD=1
if "%NEED_BUILD%"=="1" (
    echo [信息] 正在构建前端产物...
    pushd frontend
    rem vite.config.js 刻意设置 emptyOutDir=false，旧 hash 文件不会自动清理，
    rem 这里手动清空，避免历史版本的 JS/CSS 全部打进 exe 导致体积膨胀
    if exist "dist\assets" rd /s /q "dist\assets"
    call npm install --registry=https://registry.npmmirror.com --no-audit --no-fund
    call npm run build
    popd
    if errorlevel 1 (
        echo [错误] 前端构建失败
        pause
        exit /b 1
    )
) else (
    echo [信息] 前端产物已存在（跳过构建，如需重构建请运行：打包.bat rebuild）
)

echo [信息] 开始打包（约 1~3 分钟，请稍候）...
python -m PyInstaller LanShare.spec --noconfirm
if errorlevel 1 (
    echo [错误] 打包失败，请把上方错误信息反馈给开发者
    pause
    exit /b 1
)

echo.
echo ====================================
echo   打包完成！产物：dist\LanShare.exe
echo   把这个 exe 发给别人即可：
echo     无需安装 Python / Node / 任何依赖，
echo     双击运行，浏览器打开显示的地址就能用。
echo   数据会保存在 exe 同目录的 data\ 下。
echo ====================================
pause
