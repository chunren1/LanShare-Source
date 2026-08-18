@echo off
chcp 936 >nul
title LanShare 安装包制作工具
cd /d "%~dp0"

set "ISCC=C:\Program Files (x86)\Inno Setup 6\ISCC.exe"

echo ====================================
echo   LanShare 安装包制作（Inno Setup）
echo ====================================
echo.

REM 1. 前置：先保证 dist\LanShare.exe 存在（缺失时提醒先跑 打包.bat）
if not exist "dist\LanShare.exe" (
    echo [错误] 未找到 dist\LanShare.exe
    echo        请先运行「打包.bat」生成 exe，再制作安装包。
    pause
    exit /b 1
)

REM 2. 检查 Inno Setup 编译器
if exist "%ISCC%" goto REM 3. 检查中文语言文件（Inno Setup 默认只带英文，需单独下载）
if exist "ChineseSimplified.isl" goto :compile
echo [信息] 正在下载中文语言文件...
curl.exe -L -s -o "ChineseSimplified.isl" "https://raw.githubusercontent.com/jrsoftware/issrc/main/Files/Languages/ChineseSimplified.isl"
if not exist "ChineseSimplified.isl" (
    echo [错误] 中文语言文件下载失败，请手动下载并放到本目录：
    echo         https://raw.githubusercontent.com/jrsoftware/issrc/main/Files/Languages/ChineseSimplified.isl
    pause
    exit /b 1
)

:compile

echo [信息] 未检测到 Inno Setup 6，正在下载安装（约 2MB）...
set "IS_INSTALLER=%TEMP%\innosetup-installer.exe"

REM 依次尝试多个下载源（GitHub Release 优先，官方镜像备选）
curl.exe -L -s -o "%IS_INSTALLER%" "https://github.com/jrsoftware/issrc/releases/download/is-6_7_3/innosetup-6.7.3.exe"
if not exist "%IS_INSTALLER%" (
    curl.exe -L -s -o "%IS_INSTALLER%" "https://files.jrsoftware.org/is/6/innosetup-6.7.3.exe"
)
if not exist "%IS_INSTALLER%" (
    echo [错误] 自动下载失败。请手动下载并安装 Inno Setup 6：
    echo         https://github.com/jrsoftware/issrc/releases
    echo         （下载 innosetup-6.7.3.exe 后双击安装，一路下一步即可）
    pause
    exit /b 1
)

echo [信息] 正在安装 Inno Setup（会弹出 UAC 授权窗口，请点「是」）...
powershell -NoProfile -Command "Start-Process -FilePath '%IS_INSTALLER%' -ArgumentList '/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/SP-' -Verb RunAs -Wait"
if not exist "%ISCC%" (
    echo [错误] Inno Setup 安装失败，请手动安装后重试。
    pause
    exit /b 1
)

:compile
echo [信息] 正在编译安装包（约 1 分钟）...
"%ISCC%" "installer.iss"
if errorlevel 1 (
    echo [错误] 编译失败，请检查上方日志。
    pause
    exit /b 1
)

echo.
echo ====================================
echo   安装包制作完成！
echo   产物：installer\LanShare-Setup.exe
echo.
echo   发给别人后：双击 → 下一步 → 完成，
echo   桌面/开始菜单自动出现 LanShare 图标，
echo   控制面板可卸载。数据保存在
echo   %%LOCALAPPDATA%%\LanShare 下。
echo ====================================
pause
