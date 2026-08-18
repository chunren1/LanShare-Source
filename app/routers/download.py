# 下载 API：单文件下载（支持 Range 断点续传）、ZIP 打包
import urllib.parse
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse

from ..services import download_service
from ..services.file_service import FileError

router = APIRouter(prefix="/api", tags=["download"])


def _quoted_filename(name: str) -> str:
    """RFC 5987 文件名编码，支持中文"""
    return urllib.parse.quote(name)


@router.get("/download")
def download_file(path: str = Query(...)):
    """单文件下载，FileResponse 原生支持 Range 请求（断点续传）"""
    try:
        target = download_service.resolve_file(path)
    except FileError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return FileResponse(
        target,
        media_type="application/octet-stream",
        filename=target.name,
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{_quoted_filename(target.name)}"},
    )


@router.get("/download/zip")
def download_zip(paths: str = Query(..., description="多个路径用逗号分隔")):
    """多选/目录打包 ZIP 下载（流式：边打包边发送，首字节无需等待打包完成）"""
    path_list = [p for p in paths.split(",") if p.strip()]
    if not path_list:
        raise HTTPException(status_code=400, detail="未选择任何文件")

    try:
        files = download_service.collect_files(path_list)
    except FileError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # 打包名：单文件用原名，多文件用 "打包下载"
    if len(files) == 1:
        zip_name = Path(files[0][1]).stem + ".zip"
    else:
        zip_name = "打包下载.zip"

    return StreamingResponse(
        download_service.iter_zip_stream(path_list, files=files),
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{_quoted_filename(zip_name)}"},
    )
