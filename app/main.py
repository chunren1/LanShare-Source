# LanShare 主入口
import gzip
import socket
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.datastructures import Headers, MutableHeaders

from . import config
from .database import init_db
from .routers import auth, download, files, upload


class SelectiveGZipMiddleware:
    """仅对文本/JSON 类响应做 gzip 压缩。

    相比 Starlette 内置 GZipMiddleware 的差异：
    - 只压缩 text/*、application/json 等可压缩内容，不影响大文件下载
      （application/octet-stream、video/* 等）与 Range/206 响应；
    - 响应头已带 content-range（分片）或已带 content-encoding 时一律跳过；
    - content-length 明确且小于 minimum_size 的响应不压缩。

    实现要点：start 消息到达时**立即判定并转发**（不缓存），body 用
    GzipFile 逐块压缩转发。避免「缓存 start 等 body 再转发」带来的两个
    问题：304/无 body 响应 start 永远发不出去导致挂起；以及并发多块
    响应中出现重复 start 触发 ASGI 断言错误。
    """

    _COMPRESSIBLE_PREFIXES = ("text/", "application/json", "application/xml", "application/javascript")

    def __init__(self, app, minimum_size: int = 1024):
        self.app = app
        self.minimum_size = minimum_size

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = Headers(scope=scope)
        if "gzip" not in headers.get("Accept-Encoding", "").lower():
            await self.app(scope, receive, send)
            return

        import gzip
        import io

        compress = False
        gzip_file = None
        gzip_buffer = None

        async def send_with_compression(message):
            nonlocal compress, gzip_file, gzip_buffer
            if message["type"] == "http.response.start":
                h = Headers(raw=message["headers"])
                content_type = h.get("content-type", "").lower()
                try:
                    content_length = int(h.get("content-length", "0") or 0)
                except (TypeError, ValueError):
                    content_length = 0
                compress = (
                    200 <= message["status"] < 300
                    and "gzip" not in h.get("content-encoding", "").lower()
                    and "content-range" not in h
                    and any(content_type.startswith(p) for p in self._COMPRESSIBLE_PREFIXES)
                    and (content_length == 0 or content_length >= self.minimum_size)
                )
                if not compress:
                    await send(message)
                    return
                mh = MutableHeaders(raw=message["headers"])
                mh.add_vary_header("Accept-Encoding")
                mh["Content-Encoding"] = "gzip"
                try:
                    del mh["Content-Length"]
                except KeyError:
                    pass  # 无 content-length（分块传输）时无需删除
                gzip_buffer = io.BytesIO()
                gzip_file = gzip.GzipFile(mode="wb", compresslevel=6, fileobj=gzip_buffer)
                await send({"type": "http.response.start", "status": message["status"], "headers": mh.raw})
                return
            if message["type"] == "http.response.body" and compress and gzip_file is not None:
                gzip_file.write(message["body"])
                gzip_file.flush()
                body = gzip_buffer.getvalue()
                gzip_buffer.seek(0)
                gzip_buffer.truncate()
                await send(
                    {"type": "http.response.body", "body": body, "more_body": message.get("more_body", False)}
                )
                if not message.get("more_body", False):
                    gzip_file.close()
                    gzip_file = None
                return
            await send(message)

        await self.app(scope, receive, send_with_compression)


@asynccontextmanager
async def lifespan(app: FastAPI):
    config.ensure_dirs()
    init_db()
    yield


app = FastAPI(title="LanShare 局域网文件共享", version="1.0.0", lifespan=lifespan)

# CORS（开发模式下前端独立端口访问需要；生产环境同源不受影响）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)
# 文本/JSON 响应 gzip 压缩（不影响大文件下载与 ZIP 流式响应）
app.add_middleware(SelectiveGZipMiddleware, minimum_size=1024)

# 访问密码鉴权中间件（仅保护 /api 接口）
@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    path = request.url.path
    if path.startswith("/api"):
        # 放行认证相关接口
        if path.startswith("/api/auth"):
            return await call_next(request)
        if not auth.verify_token(request):
            return JSONResponse(status_code=401, content={"detail": "需要访问密码"})
    return await call_next(request)


# 注册路由
app.include_router(files.router)
app.include_router(upload.router)
app.include_router(download.router)
app.include_router(auth.router)


# 常见虚拟网卡/隧道网段前缀，获取局域网 IP 时过滤掉，避免二维码/提示指向虚拟网卡
_VIRTUAL_IP_PREFIXES = (
    "127.",        # 回环
    "169.254.",    # APIPA 自动配置
)


def _is_virtual_ip(ip: str) -> bool:
    """判断是否为虚拟网卡 / 无意义地址（回环、APIPA、常见虚拟网段）"""
    if ip.startswith(_VIRTUAL_IP_PREFIXES):
        return True
    # VMware / VirtualBox / Hyper-V 常见段：192.168.122.x、192.168.56.x、192.168.137.x 等
    if ip.startswith("192.168.122.") or ip.startswith("192.168.56.") or ip.startswith("192.168.137."):
        return True
    if ip.startswith("172.16.") or ip.startswith("172.17.") or ip.startswith("172.18."):
        return True  # Docker 默认网桥段（172.17/18 常见）
    return False


def _get_ips_via_ipconfig() -> set[str]:
    """Windows：解析 ipconfig 输出兜底获取局域网 IP（不依赖外网）。"""
    ips = set()
    if sys.platform != "win32":
        return ips
    try:
        import subprocess

        out = subprocess.run(
            ["ipconfig"], capture_output=True, text=True, timeout=10, errors="replace"
        ).stdout
        for line in out.splitlines():
            line = line.strip()
            if "IPv4" in line and ":" in line:
                candidate = line.split(":", 1)[1].strip()
                if candidate and not _is_virtual_ip(candidate):
                    ips.add(candidate)
    except Exception:
        pass
    return ips


def _get_ip_addresses() -> list[str]:
    """获取本机局域网 IP（多级 fallback，不依赖外网）。

    1. UDP 连接公网取出口 IP（外网可达时最准）；
    2. 遍历网卡（getaddrinfo）；
    3. Windows 下解析 ipconfig（内网隔离 / 无外网时兜底）。
    """
    ips = set()

    # 方法 1：UDP connect 公网（仅路由可达即可，不发真实流量）
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        if not _is_virtual_ip(ip):
            ips.add(ip)
    except OSError:
        pass

    # 方法 2：遍历网卡（getaddrinfo）
    try:
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None, socket.AF_INET):
            ip = info[4][0]
            if not _is_virtual_ip(ip):
                ips.add(ip)
    except OSError:
        pass

    # 方法 3：ipconfig 兜底（无外网 / 主机名解析失败时）
    if not ips:
        ips = _get_ips_via_ipconfig()

    return sorted(ips)


def _try_open_firewall_port() -> bool:
    """Windows：尝试用 netsh 放行当前监听端口的入站规则（需管理员权限）。

    迁移到新电脑后，Windows 防火墙默认拦截入站端口，导致局域网其他电脑
    无法访问。有权限时自动放行，无权限时静默返回 False，由调用方提示。
    """
    if sys.platform != "win32":
        return True
    try:
        import subprocess

        rule_name = f"LanShare TCP {config.PORT}"
        r = subprocess.run(
            [
                "netsh", "advfirewall", "firewall", "add", "rule",
                f"name={rule_name}",
                "dir=in", "action=allow", "protocol=TCP", f"localport={config.PORT}",
            ],
            capture_output=True, text=True, timeout=15, errors="replace",
        )
        return r.returncode == 0
    except Exception:
        return False


@app.get("/api/meta/network")
def network_info():
    """返回局域网访问地址，供二维码使用"""
    return {"ips": _get_ip_addresses(), "port": config.PORT}


# 托管前端构建产物（生产模式）
_FRONTEND_DIST = config.FRONTEND_DIST


def _mount_frontend():
    if _FRONTEND_DIST.exists():
        app.mount("/assets", StaticFiles(directory=_FRONTEND_DIST / "assets"), name="assets")

        @app.get("/{full_path:path}", include_in_schema=False)
        async def serve_spa(full_path: str):
            """SPA 回退：非 /api 路径一律返回 index.html"""
            requested = _FRONTEND_DIST / full_path
            if full_path and requested.exists() and requested.is_file():
                return FileResponse(requested)
            return FileResponse(_FRONTEND_DIST / "index.html")


_mount_frontend()


if __name__ == "__main__":
    import uvicorn

    config.ensure_dirs()
    # 尝试放行防火墙端口（Windows 下局域网其他设备能否访问的关键）
    if not _try_open_firewall_port():
        print("  [提示] 若局域网其他设备无法访问本服务，请用「管理员身份」")
        print("         运行本程序一次，或手动在防火墙中放行该端口。")
    print("=" * 50)
    print("  LanShare 局域网文件共享工具")
    print("=" * 50)
    for ip in _get_ip_addresses():
        print(f"  局域网访问: http://{ip}:{config.PORT}")
    if not _get_ip_addresses():
        print("  [警告] 未检测到局域网 IP，请检查网络连接后重启本程序")
    print(f"  本机访问  : http://127.0.0.1:{config.PORT}")
    if config.ACCESS_PASSWORD:
        print("  访问密码  : 已启用")
    print("=" * 50)
    uvicorn.run(app, host=config.HOST, port=config.PORT)
