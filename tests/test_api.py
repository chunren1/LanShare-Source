# LanShare 后端接口测试
import hashlib
import io
import os
import sys
import tempfile
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# 使用独立测试数据目录，避免污染真实数据
TEST_DATA_DIR = Path(tempfile.mkdtemp(prefix="lanshare_test_"))
os.environ["LANSHARE_DATA_DIR"] = str(TEST_DATA_DIR)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.main import app  # noqa: E402
from app import config  # noqa: E402
from app.database import init_db  # noqa: E402

# TestClient 默认不触发 lifespan，需手动初始化数据库
config.ensure_dirs()
init_db()

client = TestClient(app)

CHUNK_SIZE = 4 * 1024 * 1024


def make_test_file(size: int) -> tuple[bytes, str]:
    """生成指定大小的测试数据及其 MD5"""
    data = os.urandom(size)
    md5 = hashlib.md5(data).hexdigest()
    return data, md5


def upload_via_chunks(data: bytes, name: str, target_dir: str = "") -> dict:
    """模拟前端分片上传完整流程"""
    md5 = hashlib.md5(data).hexdigest()
    total_chunks = (len(data) + CHUNK_SIZE - 1) // CHUNK_SIZE

    init = client.post(
        "/api/upload/init",
        data={"md5": md5, "fileName": name, "totalSize": str(len(data)), "chunkSize": str(CHUNK_SIZE)},
    )
    assert init.status_code == 200, init.text
    init_data = init.json()

    if not init_data["needUpload"]:
        return init_data

    upload_id = init_data["uploadId"]
    for i in range(total_chunks):
        chunk = data[i * CHUNK_SIZE : (i + 1) * CHUNK_SIZE]
        chunk_md5 = hashlib.md5(chunk).hexdigest()
        resp = client.post(
            "/api/upload/chunk",
            data={
                "uploadId": str(upload_id),
                "chunkIndex": str(i),
                "chunkMd5": chunk_md5,
            },
            files={"file": (f"chunk-{i}", chunk, "application/octet-stream")},
        )
        assert resp.status_code == 200, resp.text

    merge = client.post("/api/upload/merge", data={"uploadId": str(upload_id), "targetDir": target_dir})
    assert merge.status_code == 200, merge.text
    return merge.json()


# ========== 文件管理 ==========

def test_mkdir_and_list():
    resp = client.post("/api/dir", json={"path": "测试目录"})
    assert resp.status_code == 200

    resp = client.get("/api/files?path=")
    assert resp.status_code == 200
    names = [f["name"] for f in resp.json()]
    assert "测试目录" in names


def test_upload_and_list_file():
    data, _ = make_test_file(1024 * 1024)  # 1MB
    result = upload_via_chunks(data, "hello.txt")
    assert result["merged"] is True

    resp = client.get("/api/files?path=")
    files = [f for f in resp.json() if not f["is_dir"]]
    assert any(f["name"] == "hello.txt" for f in files)
    assert files[0]["size"] == 1024 * 1024


def test_rename_file():
    data, _ = make_test_file(1024)
    upload_via_chunks(data, "old_name.txt")
    resp = client.post("/api/file/rename", json={"path": "old_name.txt", "newName": "new_name.txt"})
    assert resp.status_code == 200

    resp = client.get("/api/files?path=")
    names = [f["name"] for f in resp.json()]
    assert "new_name.txt" in names
    assert "old_name.txt" not in names


def test_delete_file():
    data, _ = make_test_file(1024)
    upload_via_chunks(data, "to_delete.txt")
    resp = client.delete("/api/file?path=to_delete.txt")
    assert resp.status_code == 200

    resp = client.get("/api/files?path=")
    names = [f["name"] for f in resp.json()]
    assert "to_delete.txt" not in names


def test_search():
    data, _ = make_test_file(1024)
    upload_via_chunks(data, "年度报告-2026.pdf")
    resp = client.get("/api/files/search?path=&keyword=报告")
    assert resp.status_code == 200
    assert any("报告" in f["name"] for f in resp.json())


# ========== 分片上传 / 断点续传 ==========

def test_upload_multiple_chunks():
    """5MB 文件 → 2 个分片"""
    data, md5 = make_test_file(5 * 1024 * 1024)
    result = upload_via_chunks(data, "big.bin")
    assert result["merged"] is True

    # 验证文件完整
    saved = config.FILES_DIR / "big.bin"
    assert saved.exists()
    assert hashlib.md5(saved.read_bytes()).hexdigest() == md5


def test_instant_upload():
    """重复上传相同文件 → 秒传"""
    data, _ = make_test_file(1024 * 1024)
    upload_via_chunks(data, "instant.bin")

    init = client.post(
        "/api/upload/init",
        data={"md5": hashlib.md5(data).hexdigest(), "fileName": "instant.bin", "totalSize": str(len(data)), "chunkSize": str(CHUNK_SIZE)},
    )
    assert init.status_code == 200
    assert init.json()["needUpload"] is False


def test_resume_upload():
    """断点续传：上传部分分片后查询状态，续传剩余分片"""
    data, md5 = make_test_file(10 * 1024 * 1024)  # 3 个分片
    total_chunks = (len(data) + CHUNK_SIZE - 1) // CHUNK_SIZE

    init = client.post(
        "/api/upload/init",
        data={"md5": md5, "fileName": "resume.bin", "totalSize": str(len(data)), "chunkSize": str(CHUNK_SIZE)},
    ).json()
    upload_id = init["uploadId"]

    # 只上传第 0 片
    chunk0 = data[:CHUNK_SIZE]
    resp = client.post(
        "/api/upload/chunk",
        data={"uploadId": str(upload_id), "chunkIndex": "0", "chunkMd5": hashlib.md5(chunk0).hexdigest()},
        files={"file": ("chunk-0", chunk0, "application/octet-stream")},
    )
    assert resp.status_code == 200

    # 模拟"断网重连"：重新 init 应返回已上传分片
    init2 = client.post(
        "/api/upload/init",
        data={"md5": md5, "fileName": "resume.bin", "totalSize": str(len(data)), "chunkSize": str(CHUNK_SIZE)},
    ).json()
    assert 0 in init2["uploadedChunks"]
    assert len(init2["uploadedChunks"]) == 1

    # 续传剩余分片
    for i in range(1, total_chunks):
        chunk = data[i * CHUNK_SIZE : (i + 1) * CHUNK_SIZE]
        resp = client.post(
            "/api/upload/chunk",
            data={"uploadId": str(upload_id), "chunkIndex": str(i), "chunkMd5": hashlib.md5(chunk).hexdigest()},
            files={"file": (f"chunk-{i}", chunk, "application/octet-stream")},
        )
        assert resp.status_code == 200

    merge = client.post("/api/upload/merge", data={"uploadId": str(upload_id)})
    assert merge.status_code == 200

    saved = config.FILES_DIR / "resume.bin"
    assert hashlib.md5(saved.read_bytes()).hexdigest() == md5


def test_chunk_md5_validation():
    """错误 MD5 的分片应被拒绝"""
    data, md5 = make_test_file(2 * CHUNK_SIZE)
    init = client.post(
        "/api/upload/init",
        data={"md5": md5, "fileName": "bad.bin", "totalSize": str(len(data)), "chunkSize": str(CHUNK_SIZE)},
    ).json()
    upload_id = init["uploadId"]

    chunk = data[:CHUNK_SIZE]
    resp = client.post(
        "/api/upload/chunk",
        data={"uploadId": str(upload_id), "chunkIndex": "0", "chunkMd5": "0" * 32},  # 错误 MD5
        files={"file": ("chunk-0", chunk, "application/octet-stream")},
    )
    assert resp.status_code == 400


def test_cancel_upload():
    """取消上传：清理临时分片 + 任务标记 cancelled"""
    data, md5 = make_test_file(10 * 1024 * 1024)

    init = client.post(
        "/api/upload/init",
        data={"md5": md5, "fileName": "cancel.bin", "totalSize": str(len(data)), "chunkSize": str(CHUNK_SIZE)},
    ).json()
    upload_id = init["uploadId"]

    # 上传部分分片
    chunk0 = data[:CHUNK_SIZE]
    resp = client.post(
        "/api/upload/chunk",
        data={"uploadId": str(upload_id), "chunkIndex": "0", "chunkMd5": hashlib.md5(chunk0).hexdigest()},
        files={"file": ("chunk-0", chunk0, "application/octet-stream")},
    )
    assert resp.status_code == 200

    # 记录临时目录
    from app.database import db

    with db() as conn:
        row = conn.execute("SELECT temp_dir FROM upload_tasks WHERE id=?", (upload_id,)).fetchone()
    temp_dir = Path(row["temp_dir"])
    assert temp_dir.exists()

    # 取消
    resp = client.post("/api/upload/cancel", data={"uploadId": str(upload_id)})
    assert resp.status_code == 200
    assert resp.json()["cancelled"] is True

    # 临时分片已清理
    assert not temp_dir.exists()

    # 任务标记为 cancelled
    with db() as conn:
        row = conn.execute("SELECT status FROM upload_tasks WHERE id=?", (upload_id,)).fetchone()
    assert row["status"] == "cancelled"

    # 取消后重新 init 应为新任务（needUpload=True）
    init2 = client.post(
        "/api/upload/init",
        data={"md5": md5, "fileName": "cancel.bin", "totalSize": str(len(data)), "chunkSize": str(CHUNK_SIZE)},
    ).json()
    assert init2["needUpload"] is True


def test_merge_missing_chunks_fails():
    """分片未传全时合并应报错"""
    data, md5 = make_test_file(2 * CHUNK_SIZE)
    init = client.post(
        "/api/upload/init",
        data={"md5": md5, "fileName": "partial.bin", "totalSize": str(len(data)), "chunkSize": str(CHUNK_SIZE)},
    ).json()
    upload_id = init["uploadId"]

    # 只传一片就合并
    chunk0 = data[:CHUNK_SIZE]
    client.post(
        "/api/upload/chunk",
        data={"uploadId": str(upload_id), "chunkIndex": "0", "chunkMd5": hashlib.md5(chunk0).hexdigest()},
        files={"file": ("chunk-0", chunk0, "application/octet-stream")},
    )
    resp = client.post("/api/upload/merge", data={"uploadId": str(upload_id)})
    assert resp.status_code == 400


# ========== 下载 ==========

def test_download_file():
    data, md5 = make_test_file(1024 * 1024)
    upload_via_chunks(data, "download.bin")

    resp = client.get("/api/download?path=download.bin")
    assert resp.status_code == 200
    assert hashlib.md5(resp.content).hexdigest() == md5


def test_download_range():
    """HTTP Range 断点续传下载"""
    data, _ = make_test_file(1024 * 1024)
    upload_via_chunks(data, "range.bin")

    headers = {"Range": "bytes=500000-"}
    resp = client.get("/api/download?path=range.bin", headers=headers)
    assert resp.status_code == 206
    assert len(resp.content) == 1024 * 1024 - 500000
    assert resp.content == data[500000:]


def test_download_zip():
    """多文件打包下载"""
    data1, _ = make_test_file(1024)
    data2, _ = make_test_file(2048)
    upload_via_chunks(data1, "zip_a.txt")
    upload_via_chunks(data2, "zip_b.txt")

    resp = client.get("/api/download/zip?paths=zip_a.txt,zip_b.txt")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/zip"

    zf = zipfile.ZipFile(io.BytesIO(resp.content))
    names = zf.namelist()
    assert "zip_a.txt" in names and "zip_b.txt" in names


def test_download_zip_stream_integrity():
    """流式 ZIP 打包：内容完整可解压，且文件字节一致"""
    entries = {
        "stream_a.bin": make_test_file(256 * 1024),
        "stream_b.bin": make_test_file(512 * 1024),
        "stream_c.bin": make_test_file(1024),
    }
    for name, (data, _) in entries.items():
        upload_via_chunks(data, name)

    resp = client.get("/api/download/zip?paths=" + ",".join(entries.keys()))
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/zip"

    zf = zipfile.ZipFile(io.BytesIO(resp.content))
    assert sorted(zf.namelist()) == sorted(entries.keys())
    for name, (data, _) in entries.items():
        assert zf.read(name) == data


def test_download_range_concurrent():
    """并发 Range 分片下载：多连接分段拉取后拼装与源文件一致（前端下载器核心依赖）"""
    data, md5 = make_test_file(8 * 1024 * 1024)  # 8MB
    upload_via_chunks(data, "concurrent.bin")

    n = 4
    per = (len(data) + n - 1) // n
    parts = []
    for i in range(n):
        start = i * per
        end = min(len(data) - 1, (i + 1) * per - 1)
        resp = client.get(
            "/api/download?path=concurrent.bin",
            headers={"Range": f"bytes={start}-{end}"},
        )
        assert resp.status_code == 206
        parts.append(resp.content)

    joined = b"".join(parts)
    assert hashlib.md5(joined).hexdigest() == md5


def test_download_zip_dir_structure():
    """目录打包下载：压缩包内保留目录层级"""
    data, _ = make_test_file(1024)
    # 先创建嵌套目录，再通过分片上传到该目录，模拟目录结构
    assert client.post("/api/dir", json={"path": "dir1/dir2"}).status_code == 200
    upload_via_chunks(data, "nested.txt", target_dir="dir1/dir2")

    resp = client.get("/api/download/zip?paths=dir1")
    assert resp.status_code == 200

    zf = zipfile.ZipFile(io.BytesIO(resp.content))
    names = zf.namelist()
    assert any(n.endswith("nested.txt") for n in names)
    assert zf.read(next(n for n in names if n.endswith("nested.txt"))) == data


# ========== 安全 ==========

def test_path_traversal_blocked():
    """路径穿越攻击应被拒绝"""
    resp = client.get("/api/files?path=../../../../etc")
    assert resp.status_code in (400, 404)

    resp = client.delete("/api/file?path=..%2F..%2F..%2F..%2FWindows")
    assert resp.status_code in (400, 404)


def test_invalid_filename_blocked():
    """非法文件名中的路径分隔符应被清洗，防止注入"""
    data, md5 = make_test_file(1024)
    # 完整走一遍上传流程，文件名含路径穿越尝试
    upload_via_chunks(data, "../../evil.txt")
    # 清洗后：文件名不含路径分隔符（/ \），且文件实际落在根目录（未越界）
    resp = client.get("/api/files?path=")
    names = [f["name"] for f in resp.json()]
    evil_files = [n for n in names if "evil" in n]
    assert evil_files, "清洗后的文件应出现在根目录列表中"
    assert all("/" not in n and "\\" not in n for n in evil_files), "文件名不应包含路径分隔符"


# ========== 存储 ==========

def test_storage_info():
    resp = client.get("/api/storage")
    assert resp.status_code == 200
    assert "used" in resp.json()


def test_storage_cache_invalidation():
    """存储统计缓存：TTL 命中 + 上传合并/删除后主动失效"""
    from app.services import file_service

    file_service._invalidate_storage_cache()

    # 首次调用 → 全量计算
    r1 = client.get("/api/storage").json()
    assert r1["cache"] is False
    # 重复调用 → 命中缓存
    r2 = client.get("/api/storage").json()
    assert r2["cache"] is True

    # 上传合并会主动失效缓存 → 重新计算且大小准确
    data, _ = make_test_file(8192)
    upload_via_chunks(data, "cache_size.bin")
    r3 = client.get("/api/storage").json()
    assert r3["cache"] is False
    assert r3["used"] == r2["used"] + 8192

    # 删除会主动失效缓存 → 大小回落
    client.delete("/api/file?path=cache_size.bin")
    r4 = client.get("/api/storage").json()
    assert r4["cache"] is False
    assert r4["used"] == r2["used"]
