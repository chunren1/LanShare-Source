# 通用工具：路径安全、MD5 计算、文件名清理
import hashlib
import re
from pathlib import Path

from . import config

# Windows 非法字符（跨平台统一过滤）
_INVALID_CHARS = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


def safe_join(relative_path: str | None) -> Path:
    """将用户传入的相对路径安全解析为 FILES_DIR 内的绝对路径，防止路径穿越。

    - 拒绝绝对路径、..、空路径穿越
    - 解析后必须位于 FILES_DIR 之内
    """
    rel = (relative_path or "").strip().replace("\\", "/")
    parts = []
    for p in rel.split("/"):
        if p in ("", ".", ".."):
            continue
        parts.append(p)

    target = config.FILES_DIR.joinpath(*parts) if parts else config.FILES_DIR
    try:
        target = target.resolve()
    except OSError:
        raise ValueError("非法路径")

    root = config.FILES_DIR.resolve()
    if target != root and root not in target.parents:
        raise ValueError("路径越界，禁止访问目录外文件")
    return target


def sanitize_filename(name: str) -> str:
    """清理文件名中的非法字符，防止路径注入"""
    name = _INVALID_CHARS.sub("_", name).strip()
    if not name or name in (".", ".."):
        raise ValueError("非法文件名")
    # 去掉文件名中的路径分隔符残留
    name = name.replace("/", "_").replace("\\", "_")
    # 防止清洗后以 . 开头（会被列表当作隐藏文件过滤，导致"传了看不见"）
    while name.startswith("."):
        name = "_" + name.lstrip(".")
    return name


def md5_of_bytes(data: bytes) -> str:
    return hashlib.md5(data).hexdigest()


def md5_of_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        while True:
            block = f.read(chunk_size)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


def format_size(num: int) -> str:
    """字节数格式化为可读字符串"""
    size = float(num)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            if unit == "B":
                return f"{int(size)} B"
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{num} B"


def get_relative_path(abs_path: Path) -> str:
    """绝对路径转相对路径（相对 FILES_DIR），用于前端展示"""
    return str(abs_path.relative_to(config.FILES_DIR)).replace("\\", "/")
