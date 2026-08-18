# LanShare 配置文件
import os
import sys
from pathlib import Path

# 是否为 PyInstaller 打包后的运行环境
IS_FROZEN = getattr(sys, "frozen", False)

if IS_FROZEN:
    # 打包后：exe 所在目录作为应用目录（数据存放于此，重启不丢失）
    APP_DIR = Path(sys.executable).resolve().parent
    # 前端静态资源被 PyInstaller 解压到临时目录
    FRONTEND_DIST = Path(getattr(sys, "_MEIPASS", APP_DIR)) / "frontend_dist"

    # 安装版（Inno Setup 装到 Program Files 等只读目录）下 exe 目录不可写，
    # 数据目录自动回退到 %LOCALAPPDATA%\LanShare，避免启动即写入失败。
    # 便携版（exe 随便放）不受影响，数据仍在 exe 旁。
    _default_data = APP_DIR / "data"
    try:
        _default_data.mkdir(parents=True, exist_ok=True)
        _probe = _default_data / ".lanshare_probe"
        _probe.write_bytes(b"")
        _probe.unlink()
    except OSError:
        _local = os.environ.get("LOCALAPPDATA") or str(Path.home())
        _default_data = Path(_local) / "LanShare"
else:
    # 源码运行：项目根目录
    APP_DIR = Path(__file__).resolve().parent.parent
    FRONTEND_DIST = APP_DIR / "frontend" / "dist"
    _default_data = APP_DIR / "data"

# 数据目录（可通过环境变量覆盖，如 LANSHARE_DATA_DIR=D:/lanshare-data）
DATA_DIR = Path(os.getenv("LANSHARE_DATA_DIR", str(_default_data)))
FILES_DIR = DATA_DIR / "files"          # 正式文件存储目录
TMP_DIR = DATA_DIR / "tmp"              # 分片临时目录
DB_PATH = DATA_DIR / "lanshare.db"      # SQLite 数据库
# 日志随数据目录走：安装版不会因 Program Files 只读而写日志失败
LOG_DIR = DATA_DIR / "logs"

# 服务监听配置
HOST = os.getenv("LANSHARE_HOST", "0.0.0.0")
PORT = int(os.getenv("LANSHARE_PORT", "8000"))

# 访问密码（为空 = 不启用访问限制）
ACCESS_PASSWORD = os.getenv("LANSHARE_PASSWORD", "")

# 上传分片大小（默认 4MB）
CHUNK_SIZE = int(os.getenv("LANSHARE_CHUNK_SIZE", str(4 * 1024 * 1024)))
# 同时上传的并发分片数
MAX_CONCURRENT_CHUNKS = int(os.getenv("LANSHARE_MAX_CONCURRENT", "3"))
# 单文件大小上限（默认 100GB）
MAX_FILE_SIZE = int(os.getenv("LANSHARE_MAX_FILE_SIZE", str(100 * 1024 * 1024 * 1024)))


def ensure_dirs():
    """确保数据目录存在"""
    for d in (FILES_DIR, TMP_DIR, LOG_DIR):
        d.mkdir(parents=True, exist_ok=True)
