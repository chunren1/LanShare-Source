# 下载服务：流式下载、ZIP 打包
import os
import shutil
import tempfile
import threading
import time
import zipfile
from pathlib import Path

from .. import config, utils
from .file_service import FileError


def resolve_file(rel_path: str) -> Path:
    """解析下载路径，仅允许文件"""
    target = utils.safe_join(rel_path)
    if not target.exists():
        raise FileError("文件不存在")
    if not target.is_file():
        raise FileError("目标不是文件")
    return target


def collect_files(paths: list[str]) -> list[tuple[Path, str]]:
    """收集所有待打包文件：[(绝对路径, 压缩包内相对路径)]"""
    files_to_zip: list[tuple[Path, str]] = []

    for rel in paths:
        target = utils.safe_join(rel)
        if not target.exists():
            continue
        if target.is_file():
            files_to_zip.append((target, target.name))
        else:
            # 目录递归（限制遍历深度，防止恶意深层目录）
            for f in sorted(target.rglob("*")):
                if f.is_file():
                    files_to_zip.append((f, f.relative_to(target.parent).as_posix()))

    if not files_to_zip:
        raise FileError("没有可打包的文件")
    return files_to_zip


def build_zip_file(paths: list[str]) -> tuple[Path, list[tuple[Path, str]]]:
    """将多个文件/目录打包为 ZIP 临时文件。

    关键设计：写入磁盘临时文件而非内存 BytesIO，
    避免打包大文件（如 8GB 视频）时内存溢出。
    """
    files_to_zip = collect_files(paths)

    # 在临时目录创建 ZIP 文件（使用 ZIP_STORED 不压缩，速度最快，避免 CPU 瓶颈）
    fd, tmp_name = tempfile.mkstemp(prefix="lanshare_zip_", suffix=".zip")
    os.close(fd)
    tmp_zip = Path(tmp_name)
    try:
        with zipfile.ZipFile(tmp_zip, "w", zipfile.ZIP_STORED) as zf:
            for path, arcname in files_to_zip:
                zf.write(path, arcname)
    except Exception:
        tmp_zip.unlink(missing_ok=True)
        raise

    return tmp_zip, files_to_zip


def cleanup_zip_file(tmp_zip: Path):
    """响应发送完成后清理临时 ZIP 文件"""
    try:
        tmp_zip.unlink(missing_ok=True)
    except OSError:
        pass


def iter_zip_stream(paths: list[str], files: list[tuple[Path, str]] | None = None, read_chunk: int = 1024 * 1024):
    """流式 ZIP 打包迭代器：边打包边发送，首字节无需等待整个目录打包完成。

    设计要点：
    - 仍写入磁盘临时文件（ZIP_STORED 不压缩，避免大文件占内存/CPU）；
    - 后台线程负责打包，主生成器按已写入位置增量读取并 yield，首字节在首个文件落盘后即发出；
    - 异常时自动清理临时文件；响应中断时由 finally 兜底删除。
    """
    files_to_zip = files if files is not None else collect_files(paths)

    fd, tmp_name = tempfile.mkstemp(prefix="lanshare_zip_", suffix=".zip")
    os.close(fd)
    tmp_zip = Path(tmp_name)

    written = 0
    error: Exception | None = None
    lock = threading.Lock()

    def _writer():
        nonlocal written, error
        try:
            with zipfile.ZipFile(tmp_zip, "w", zipfile.ZIP_STORED) as zf:
                for path, arcname in files_to_zip:
                    zf.write(path, arcname)
                    # 写一个文件即 flush 并发布新位置，供读取端增量读取
                    zf.fp.flush()
                    with lock:
                        written = zf.fp.tell()
            with lock:
                written = tmp_zip.stat().st_size
        except Exception as e:  # noqa: BLE001
            with lock:
                error = e

    thread = threading.Thread(target=_writer, daemon=True)
    thread.start()

    read_pos = 0
    try:
        with open(tmp_zip, "rb") as f:
            while True:
                with lock:
                    current_error = error
                    current_written = written
                if current_error is not None:
                    raise current_error
                if current_written > read_pos:
                    f.seek(read_pos)
                    data = f.read(min(read_chunk, current_written - read_pos))
                    if data:
                        read_pos += len(data)
                        yield data
                        continue
                if not thread.is_alive() and current_written == read_pos:
                    # 写入线程已结束且无新数据 → 全部读完
                    break
                time.sleep(0.02)
    finally:
        thread.join(timeout=5)
        try:
            tmp_zip.unlink(missing_ok=True)
        except OSError:
            pass
