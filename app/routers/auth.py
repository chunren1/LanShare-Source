# 访问密码认证 API（可选）
import secrets

from fastapi import APIRouter, HTTPException, Request

from .. import config

router = APIRouter(prefix="/api/auth", tags=["auth"])

# 内存 token 表：token -> 是否有效（重启失效，家用场景足够）
_ACTIVE_TOKENS: set[str] = set()


def is_enabled() -> bool:
    return bool(config.ACCESS_PASSWORD)


def verify_token(request: Request) -> bool:
    """校验请求是否携带有效 token"""
    if not is_enabled():
        return True
    token = request.headers.get("X-Auth-Token", "")
    return token in _ACTIVE_TOKENS


@router.post("/verify")
def verify(body: dict):
    """校验访问密码，成功返回 token"""
    if not is_enabled():
        return {"enabled": False}
    password = body.get("password", "")
    if secrets.compare_digest(password, config.ACCESS_PASSWORD):
        token = secrets.token_hex(16)
        _ACTIVE_TOKENS.add(token)
        return {"enabled": True, "token": token}
    raise HTTPException(status_code=401, detail="密码错误")


@router.get("/status")
def auth_status():
    return {"enabled": is_enabled()}
