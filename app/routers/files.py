# 文件列表与管理 API
from fastapi import APIRouter, HTTPException, Query

from ..services import file_service

router = APIRouter(prefix="/api", tags=["files"])


def _handle(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except file_service.FileError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/files")
def get_files(path: str = Query("", description="相对路径，空=根目录")):
    return _handle(file_service.list_dir, path)


@router.get("/files/search")
def search_files(path: str = Query(""), keyword: str = Query("", min_length=1)):
    return _handle(file_service.search, path, keyword)


@router.post("/dir")
def create_dir(body: dict):
    path = body.get("path", "")
    return _handle(file_service.mkdir, path)


@router.delete("/file")
def delete_file(path: str = Query(...)):
    return _handle(file_service.delete, path)


@router.post("/file/rename")
def rename_file(body: dict):
    path = body.get("path", "")
    new_name = body.get("newName", "")
    return _handle(file_service.rename, path, new_name)


@router.get("/storage")
def storage():
    return file_service.storage_info()
