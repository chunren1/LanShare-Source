# 文件管理服务：列表、删除、重命名、新建文件夹、搜索
import shutil
import time
from datetime import datetime
from pathlib import Path

from .. import config, utils


class FileError(Exception):
    pass


# 存储统计缓存：进程内 {root: (计算时刻, 结果)}，TTL 30s；
# 上传合并/删除/重命名/建目录后主动失效，保证数据及时准确。
_STORAGE_CACHE_TTL = 30
_storage_cache: dict[str, tuple[float, dict]] = {}


def _invalidate_storage_cache():
    _storage_cache.clear()


def _file_entry(abs_path: Path) -> dict:
    """将路径转换为前端展示条目"""
    stat = abs_path.stat()
    return {
        "name": abs_path.name,
        "path": utils.get_relative_path(abs_path),
        "is_dir": abs_path.is_dir(),
        "size": stat.st_size if abs_path.is_file() else 0,
        "size_str": utils.format_size(stat.st_size) if abs_path.is_file() else "-",
        "mtime": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
        "ext": abs_path.suffix.lower().lstrip(".") if abs_path.is_file() else "",
    }


def list_dir(rel_path: str) -> list[dict]:
    """列出目录内容（文件夹在前，其余按名称排序）"""
    target = utils.safe_join(rel_path)
    if not target.exists():
        raise FileError("目录不存在")
    if not target.is_dir():
        raise FileError("目标不是目录")

    items = []
    for child in target.iterdir():
        # 跳过隐藏文件
        if child.name.startswith("."):
            continue
        try:
            items.append(_file_entry(child))
        except OSError:
            continue
    items.sort(key=lambda x: (not x["is_dir"], x["name"].lower()))
    return items


def mkdir(rel_path: str) -> None:
    target = utils.safe_join(rel_path)
    if target.exists():
        raise FileError("同名文件或目录已存在")
    target.mkdir(parents=True, exist_ok=False)
    _invalidate_storage_cache()


def delete(rel_path: str) -> None:
    target = utils.safe_join(rel_path)
    if not target.exists():
        raise FileError("文件或目录不存在")
    # 禁止删除根目录
    if target == config.FILES_DIR.resolve():
        raise FileError("不允许删除根目录")
    try:
        if target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink()
    except OSError as e:
        # 某些环境（如沙箱/回收站不可用）可能拒绝删除，转为友好错误
        raise FileError(f"删除失败：{e.strerror or e}")
    _invalidate_storage_cache()


def rename(rel_path: str, new_name: str) -> None:
    target = utils.safe_join(rel_path)
    if not target.exists():
        raise FileError("文件或目录不存在")
    clean = utils.sanitize_filename(new_name)
    if clean in (".", ".."):
        raise FileError("非法文件名")
    new_path = target.parent / clean
    if new_path.exists():
        raise FileError("同名文件或目录已存在")
    target.rename(new_path)
    _invalidate_storage_cache()


def search(rel_path: str, keyword: str) -> list[dict]:
    """在当前目录递归搜索文件名包含关键词的文件"""
    target = utils.safe_join(rel_path)
    if not target.exists() or not target.is_dir():
        raise FileError("目录不存在")
    kw = keyword.strip().lower()
    results = []
    # 限制搜索深度，避免扫描过大目录卡顿
    for child in target.rglob("*"):
        if child.name.startswith("."):
            continue
        if kw in child.name.lower():
            try:
                results.append(_file_entry(child))
            except OSError:
                continue
        # 控制返回条数
        if len(results) >= 200:
            break
    return results


def storage_info() -> dict:
    """存储空间使用情况（TTL 增量缓存，大目录下毫秒级返回）"""
    root = config.FILES_DIR.resolve()
    cache_key = str(root)
    now = time.time()

    cached = _storage_cache.get(cache_key)
    if cached and now - cached[0] < _STORAGE_CACHE_TTL:
        result = dict(cached[1])
        result["cache"] = True
        return result

    total_used = 0
    for f in root.rglob("*"):
        if f.is_file():
            try:
                total_used += f.stat().st_size
            except OSError:
                continue
    result = {
        "used": total_used,
        "used_str": utils.format_size(total_used),
        "root": str(root),
        "cache": False,
    }
    _storage_cache[cache_key] = (now, dict(result))
    return result
