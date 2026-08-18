#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""LanShare 一键启动器（跨平台：Windows / macOS / Linux）。

职责（"真一键"）：
1. 自动检查后端依赖（requirements.txt），缺失时自动安装；
2. 检查前端 dist 产物，缺失时自动构建（需要 Node.js，无 Node 时降级警告）；
3. 检查端口占用并给出处理建议；
4. 打印局域网 / 本机访问地址；
5. 启动 FastAPI 服务，Ctrl+C 优雅退出。

用法：
- Windows：双击「启动.bat」（推荐，解决双击关联与中文编码问题）；
- 或直接命令行执行：python start.py
"""
import os
import shutil
import socket
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FRONTEND_DIR = ROOT / "frontend"
FRONTEND_DIST = FRONTEND_DIR / "dist"
PIP_MIRROR = os.getenv("PIP_MIRROR", "https://pypi.tuna.tsinghua.edu.cn/simple")
NPM_MIRROR = os.getenv("NPM_MIRROR", "https://registry.npmmirror.com")

# Windows 控制台统一 UTF-8 输出，避免中文乱码
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def _info(msg: str):
    print(f"[信息] {msg}")


def _warn(msg: str):
    print(f"[警告] {msg}")


def _error(msg: str):
    print(f"[错误] {msg}")


def _run(cmd: list[str], cwd: str | None = None):
    """执行命令，输出实时透出；失败抛异常"""
    subprocess.run(cmd, cwd=cwd, check=True)


def ensure_backend_deps():
    """检查后端依赖，缺失则自动安装"""
    try:
        import fastapi  # noqa: F401
        import multipart  # noqa: F401
        import uvicorn  # noqa: F401
        return
    except ImportError:
        pass
    _info("首次运行：正在安装后端依赖...")
    _run([sys.executable, "-m", "pip", "install", "-r", str(ROOT / "requirements.txt"), "-i", PIP_MIRROR])


def ensure_frontend():
    """前端 dist 缺失时自动构建（可选依赖 Node.js，缺失则降级警告）"""
    if not FRONTEND_DIR.exists() or not FRONTEND_DIR.joinpath("package.json").exists():
        return
    if FRONTEND_DIST.joinpath("index.html").exists():
        return  # 已有构建产物
    node = shutil.which("node")
    npm = shutil.which("npm")
    if not node or not npm:
        _warn("未检测到 Node.js，无法构建前端页面。请安装 Node.js 18+ 后重新运行。")
        return
    if not FRONTEND_DIR.joinpath("node_modules").exists():
        _info("首次运行：正在安装前端依赖...")
        _run([npm, "install", "--registry=" + NPM_MIRROR, "--no-audit", "--no-fund"], cwd=str(FRONTEND_DIR))
    _info("正在构建前端产物...")
    _run([npm, "run", "build"], cwd=str(FRONTEND_DIR))


def port_in_use(port: int) -> bool:
    """检查本地端口是否已被占用"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1)
        return s.connect_ex(("127.0.0.1", port)) == 0


def get_local_ips() -> list[str]:
    """获取本机局域网 IP（与 app.main 逻辑保持一致）"""
    from app.main import _get_ip_addresses  # 复用后端实现

    return _get_ip_addresses()


def main():
    from app import config  # 延迟导入：确保环境变量在 import 前已被读取

    print("=" * 56)
    print("   LanShare 局域网文件共享工具 · 一键启动")
    print("=" * 56)

    ensure_backend_deps()
    ensure_frontend()

    if port_in_use(config.PORT):
        _warn(f"端口 {config.PORT} 已被占用。")
        _warn("  可能是旧实例仍在运行，或该端口被其他程序占用。")
        _warn(f"  如需更换端口：先关闭占用进程，或设置环境变量 LANSHARE_PORT=新端口 后重试。")
        print()

    for ip in get_local_ips():
        print(f"   局域网访问: http://{ip}:{config.PORT}")
    print(f"   本机访问  : http://127.0.0.1:{config.PORT}")
    if config.ACCESS_PASSWORD:
        print("   访问密码  : 已启用")
    print("=" * 56)
    print("   关闭本窗口或按 Ctrl+C 即可停止服务")
    print("=" * 56)
    print()

    import uvicorn

    uvicorn.run("app.main:app", host=config.HOST, port=config.PORT, log_level="info")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[已退出] LanShare 服务已停止，再见！")
    except Exception as e:
        _error(str(e))
        sys.exit(1)
