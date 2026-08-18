# 上传服务：分片上传、断点续传、秒传、合并
import json
import shutil
import uuid
from pathlib import Path

from .. import config, utils
from ..database import db
from .file_service import _invalidate_storage_cache


class UploadError(Exception):
    pass


def init_upload(md5: str, file_name: str, total_size: int, chunk_size: int) -> dict:
    """上传初始化。

    - 校验参数合法性
    - 若文件已存在（同名+同MD5）→ 秒传
    - 否则创建/复用 upload_tasks 记录，返回已上传分片列表
    """
    if not md5 or len(md5) != 32:
        raise UploadError("MD5 校验值无效")
    clean_name = utils.sanitize_filename(file_name)
    if not clean_name:
        raise UploadError("文件名非法")
    if total_size <= 0:
        raise UploadError("文件大小非法")
    if total_size > config.MAX_FILE_SIZE:
        raise UploadError(f"文件超过大小上限 {utils.format_size(config.MAX_FILE_SIZE)}")
    if chunk_size <= 0:
        chunk_size = config.CHUNK_SIZE

    total_chunks = (total_size + chunk_size - 1) // chunk_size

    # 秒传判断：目标文件已存在且 MD5 一致
    with db() as conn:
        row = conn.execute(
            "SELECT * FROM upload_tasks WHERE md5=? AND file_name=? AND status='done'",
            (md5, clean_name),
        ).fetchone()

    if row:
        target = utils.safe_join(row["target_path"])
        if target.exists() and utils.md5_of_file(target) == md5:
            return {
                "uploadId": row["id"],
                "needUpload": False,
                "totalChunks": row["total_chunks"],
                "uploadedChunks": list(range(row["total_chunks"])),
            }

    # 创建或复用进行中的任务
    with db() as conn:
        row = conn.execute(
            "SELECT * FROM upload_tasks WHERE md5=? AND file_name=? AND status IN ('uploading','merging')",
            (md5, clean_name),
        ).fetchone()
        if row:
            upload_id = row["id"]
            uploaded = json.loads(row["uploaded_chunks"])
            conn.execute(
                "UPDATE upload_tasks SET total_size=?, chunk_size=?, total_chunks=?, updated_at=datetime('now','localtime') WHERE id=?",
                (total_size, chunk_size, total_chunks, upload_id),
            )
        else:
            temp_dir = config.TMP_DIR / uuid.uuid4().hex
            temp_dir.mkdir(parents=True, exist_ok=True)
            cur = conn.execute(
                "INSERT INTO upload_tasks (md5, file_name, total_size, chunk_size, total_chunks, uploaded_chunks, target_path, temp_dir) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (md5, clean_name, total_size, chunk_size, total_chunks, "[]", "", str(temp_dir)),
            )
            upload_id = cur.lastrowid
            uploaded = []

    return {
        "uploadId": upload_id,
        "needUpload": True,
        "totalChunks": total_chunks,
        "uploadedChunks": uploaded,
    }


def save_chunk(upload_id: int, chunk_index: int, data: bytes, chunk_md5: str) -> dict:
    """保存单个分片，校验 MD5，更新进度"""
    with db() as conn:
        row = conn.execute("SELECT * FROM upload_tasks WHERE id=?", (upload_id,)).fetchone()
    if not row:
        raise UploadError("上传任务不存在")
    if row["status"] == "done":
        return {"chunkIndex": chunk_index, "alreadyExists": True}

    if chunk_index < 0 or chunk_index >= row["total_chunks"]:
        raise UploadError("分片序号越界")

    # MD5 校验
    actual_md5 = utils.md5_of_bytes(data)
    if chunk_md5 and actual_md5 != chunk_md5:
        raise UploadError(f"分片 {chunk_index} MD5 校验失败")

    temp_dir = Path(row["temp_dir"])
    temp_dir.mkdir(parents=True, exist_ok=True)
    chunk_path = temp_dir / f"{chunk_index}.chunk"
    with open(chunk_path, "wb") as f:
        f.write(data)

    # 更新已上传分片
    uploaded = set(json.loads(row["uploaded_chunks"]))
    uploaded.add(chunk_index)
    uploaded_list = sorted(uploaded)
    with db() as conn:
        conn.execute(
            "UPDATE upload_tasks SET uploaded_chunks=?, status='uploading', updated_at=datetime('now','localtime') WHERE id=?",
            (json.dumps(uploaded_list), upload_id),
        )
    return {"chunkIndex": chunk_index, "alreadyExists": False}


def cancel_upload(upload_id: int) -> dict:
    """取消上传：清理临时分片，标记任务为 cancelled。

    前端点「取消」后调用，删除 temp_dir 释放磁盘空间，
    之后重新上传同一文件会作为新任务处理（分片全量重传）。
    """
    with db() as conn:
        row = conn.execute("SELECT * FROM upload_tasks WHERE id=?", (upload_id,)).fetchone()
    if not row:
        raise UploadError("上传任务不存在")

    # 清理临时分片目录（无论任务处于什么状态）
    temp_dir = Path(row["temp_dir"])
    shutil.rmtree(temp_dir, ignore_errors=True)

    with db() as conn:
        conn.execute(
            "UPDATE upload_tasks SET status='cancelled', uploaded_chunks='[]', updated_at=datetime('now','localtime') WHERE id=?",
            (upload_id,),
        )
    return {"cancelled": True, "uploadId": upload_id}


def get_status(upload_id: int) -> dict:
    """查询上传状态（断点续传恢复点）"""
    with db() as conn:
        row = conn.execute("SELECT * FROM upload_tasks WHERE id=?", (upload_id,)).fetchone()
    if not row:
        raise UploadError("上传任务不存在")
    return {
        "uploadId": row["id"],
        "md5": row["md5"],
        "fileName": row["file_name"],
        "totalSize": row["total_size"],
        "totalChunks": row["total_chunks"],
        "uploadedChunks": json.loads(row["uploaded_chunks"]),
        "status": row["status"],
    }


def merge_upload(upload_id: int, target_dir: str) -> dict:
    """合并分片为完整文件，校验整体 MD5，移入正式目录"""
    with db() as conn:
        row = conn.execute("SELECT * FROM upload_tasks WHERE id=?", (upload_id,)).fetchone()
    if not row:
        raise UploadError("上传任务不存在")
    if row["status"] == "done":
        return {"merged": True, "filePath": row["target_path"]}

    temp_dir = Path(row["temp_dir"])
    uploaded = set(json.loads(row["uploaded_chunks"]))
    total = row["total_chunks"]

    # 检查是否所有分片都已上传
    missing = [i for i in range(total) if i not in uploaded]
    if missing:
        raise UploadError(f"仍有分片未上传: {missing[:10]}")

    with db() as conn:
        conn.execute(
            "UPDATE upload_tasks SET status='merging', updated_at=datetime('now','localtime') WHERE id=?",
            (upload_id,),
        )

    # 合并
    target_dir_path = utils.safe_join(target_dir)
    if not target_dir_path.is_dir():
        target_dir_path = config.FILES_DIR
    target_file = target_dir_path / row["file_name"]
    if target_file.exists():
        # 同名文件处理：加序号
        stem = target_file.stem
        suffix = target_file.suffix
        i = 1
        while target_file.exists():
            target_file = target_dir_path / f"{stem} ({i}){suffix}"
            i += 1

    try:
        with open(target_file, "wb") as out:
            for i in range(total):
                chunk_path = temp_dir / f"{i}.chunk"
                if not chunk_path.exists():
                    raise UploadError(f"分片 {i} 文件缺失")
                with open(chunk_path, "rb") as c:
                    shutil.copyfileobj(c, out, length=1024 * 1024)

        # 整体 MD5 校验
        final_md5 = utils.md5_of_file(target_file)
        if final_md5 != row["md5"]:
            target_file.unlink(missing_ok=True)
            raise UploadError("合并后文件 MD5 与源文件不一致，上传失败")

        # 清理临时目录
        shutil.rmtree(temp_dir, ignore_errors=True)

        rel_path = utils.get_relative_path(target_file)
        with db() as conn:
            conn.execute(
                "UPDATE upload_tasks SET status='done', target_path=?, updated_at=datetime('now','localtime') WHERE id=?",
                (rel_path, upload_id),
            )
        # 合并完成后文件系统变化，主动失效存储统计缓存
        _invalidate_storage_cache()
        return {"merged": True, "filePath": rel_path, "name": target_file.name}
    except Exception:
        with db() as conn:
            conn.execute(
                "UPDATE upload_tasks SET status='failed', updated_at=datetime('now','localtime') WHERE id=?",
                (upload_id,),
            )
        raise
