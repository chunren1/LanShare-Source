#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""LanShare 打包版入口（PyInstaller frozen 环境专用）。

PyInstaller 打成单文件 exe 后，`app` 包作为模块被打进归档，由
PyInstaller 运行时自动解包，这里直接静态导入即可（打包器能据此
分析出完整依赖树，无需 -m 方式启动）。

数据目录不受影响：config.APP_DIR 在 frozen 下取 exe 所在目录，
data/ 落在 exe 旁边，重启不丢数据。

启动兜底：所有异常都会被捕获 —— 打印错误、写入 exe 旁的
lanshare-error.log、并等待按键，避免双击 exe 时窗口一闪而过
导致用户看不到失败原因（最常见：端口被占用 / 目录无写权限）。
"""
import sys
from pathlib import Path

# 控制台 UTF-8 输出，避免中文乱码
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def _error_log_path() -> Path:
    """错误日志落盘位置：跟随数据目录（安装版 exe 目录可能只读，写不进去）"""
    from app import config

    return config.DATA_DIR / "lanshare-error.log"


def _fail(msg: str, detail: str = ""):
    """打印错误并落盘，等待按键，窗口不闪退"""
    print(f"\n[错误] {msg}")
    log = _error_log_path()
    try:
        log.write_text(f"[LanShare 启动失败]\n{msg}\n\n{detail}", encoding="utf-8")
        print(f"  详情已写入: {log}")
    except Exception:
        pass
    try:
        input("\n按回车键关闭本窗口...")
    except Exception:
        pass


def main():
    from app import config
    from app import main as app_main  # 模块对象（注意：别 from 导入函数名，会覆盖本文件 main）
    import uvicorn

    config.ensure_dirs()
    # 尝试放行防火墙端口（Windows 下局域网其他设备能否访问的关键）
    if not app_main._try_open_firewall_port():
        print("  [提示] 若局域网其他设备无法访问本服务，请用「管理员身份」")
        print("         运行本程序一次，或手动在防火墙中放行该端口。")
    print("=" * 50)
    print("  LanShare 局域网文件共享工具")
    print("=" * 50)
    for ip in app_main._get_ip_addresses():
        print(f"  局域网访问: http://{ip}:{config.PORT}")
    if not app_main._get_ip_addresses():
        print("  [警告] 未检测到局域网 IP，请检查网络连接后重启本程序")
    print(f"  本机访问  : http://127.0.0.1:{config.PORT}")
    if config.ACCESS_PASSWORD:
        print("  访问密码  : 已启用")
    print("=" * 50)
    print("  关闭本窗口或按 Ctrl+C 即可停止服务")
    print("=" * 50)
    uvicorn.run(app_main.app, host=config.HOST, port=config.PORT, log_level="info")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[已退出] LanShare 服务已停止，再见！")
    except SystemExit as e:
        # uvicorn 在端口被占用等场景可能抛 SystemExit
        msg = str(e) or "服务启动失败（端口被占用或系统环境异常）"
        _fail(msg)
    except Exception as e:
        import traceback

        _fail(f"启动失败：{e}", traceback.format_exc())
