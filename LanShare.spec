# -*- mode: python ; coding: utf-8 -*-
"""LanShare.spec —— PyInstaller 单文件打包配置。

在项目根目录执行：
    pyinstaller LanShare.spec --noconfirm
或直接双击「打包.bat」一键完成（自动装 PyInstaller + 构建前端 + 打包）。

产物：dist/LanShare.exe（单文件，对方电脑零依赖双击即用）。

关键点：
1. 入口用 launcher.py（见其注释，规避 frozen 下的 -m 相对导入问题）；
2. 前端 dist/ 以数据目录 frontend_dist 打进包内，与 app/config.py 的
   IS_FROZEN 分支（_MEIPASS/frontend_dist）对应；
3. hiddenimports 补齐 uvicorn 动态加载的协议/循环/生命周期模块；
4. 排除 uvloop 等 Windows 无用模块，控制体积。
"""
import importlib.util
import os

ROOT = os.path.abspath(os.getcwd())

# uvicorn 采用“动态导入”加载协议与循环实现，PyInstaller 静态分析不到，
# 必须显式声明。这里按环境实际安装情况收集（缺失的不会报错，仅提示）。
_UVICORN_DYNAMIC = [
    "uvicorn.logging",
    "uvicorn.loops.auto",
    "uvicorn.loops.asyncio",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.protocols.websockets.websockets_impl",
    "uvicorn.protocols.websockets.wsproto_impl",
    "uvicorn.lifespan.on",
    "uvicorn.lifespan.off",
]
_UVICORN_EXTRA = [
    "httptools",
    "websockets",
    "wsproto",
    "watchfiles",
]
hiddenimports = list(_UVICORN_DYNAMIC)
for _m in _UVICORN_EXTRA:
    if importlib.util.find_spec(_m):
        hiddenimports.append(_m)

a = Analysis(
    ["launcher.py"],
    pathex=[ROOT],
    binaries=[],
    datas=[
        (os.path.join(ROOT, "frontend", "dist"), "frontend_dist"),
    ],
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        # Windows 上 uvloop 不可用，排除避免误打包
        "uvloop",
        # 不需要的 stdlib 模块，缩小体积
        "tkinter",
        "unittest",
        "pydoc",
        "doctest",
        "test",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="LanShare",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,          # 保留控制台窗口：显示局域网访问地址
    disable_windowed_traceback=False,
    icon=os.path.join(ROOT, "icons", "lanshare.ico"),
)
