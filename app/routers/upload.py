# 上传 API：分片上传 / 断点续传 / 秒传
from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from ..services import upload_service

router = APIRouter(prefix="/api/upload", tags=["upload"])


def _handle(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except upload_service.UploadError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/init")
def init_upload(
    md5: str = Form(...),
    fileName: str = Form(...),
    totalSize: int = Form(...),
    chunkSize: int = Form(0),
):
    return _handle(upload_service.init_upload, md5, fileName, totalSize, chunkSize)


@router.post("/chunk")
async def upload_chunk(
    uploadId: int = Form(...),
    chunkIndex: int = Form(...),
    chunkMd5: str = Form(""),
    file: UploadFile = File(...),
):
    data = await file.read()
    return _handle(upload_service.save_chunk, uploadId, chunkIndex, data, chunkMd5)


@router.get("/status")
def upload_status(uploadId: int):
    return _handle(upload_service.get_status, uploadId)


@router.post("/merge")
def merge_upload(uploadId: int = Form(...), targetDir: str = Form("")):
    return _handle(upload_service.merge_upload, uploadId, targetDir)


@router.post("/cancel")
def cancel_upload(uploadId: int = Form(...)):
    """取消上传：清理临时分片并标记任务为 cancelled"""
    return _handle(upload_service.cancel_upload, uploadId)
