# LanShare 局域网文件共享工具

在同一个局域网内，让电脑、手机、平板通过浏览器互相上传/下载文件的轻量工具。
无需外网、无需安装客户端，启动一条命令即可使用。

## 功能特性

- ✅ **大文件分片上传**：4MB/片，支持几十 GB 大文件
- ✅ **断点续传**：网络中断后重新上传，自动跳过已传分片
- ✅ **秒传**：重复上传相同文件，瞬间完成
- ✅ **断点续传下载**：服务端支持 HTTP Range，下载中断可续传
- ✅ **文件管理**：文件夹浏览、新建、重命名、删除、搜索
- ✅ **打包下载**：多选文件/整个目录打包为 ZIP
- ✅ **在线预览**：图片、视频、音频、PDF、文本
- ✅ **二维码访问**：手机扫码直达
- ✅ **访问密码**：可选设置访问密码
- ✅ **移动端适配**：手机浏览器自适应

## 快速开始

### 环境要求

- Python 3.10+
- Node.js 18+（仅构建前端时需要）

### 1. 安装后端依赖

```bash
pip install -r requirements.txt
```

### 2. 构建前端

```bash
cd frontend
npm install
npm run build
cd ..
```

### 3. 启动服务

```bash
python -m app.main
```

启动后终端会打印局域网访问地址，如 `http://192.168.1.100:8000`。
**手机浏览器扫码首页右上角二维码，即可上传/下载文件。**

## 配置

通过环境变量配置（Windows 用 `set`，macOS/Linux 用 `export`）。支持 `.env` 文件（项目根目录，同 `app/config.py` 读取逻辑）：

| 变量 | 说明 | 默认值 |
| --- | --- | --- |
| `LANSHARE_PORT` | 服务端口 | `8000` |
| `LANSHARE_DATA_DIR` | 数据存储目录 | `./data` |
| `LANSHARE_PASSWORD` | 访问密码（空=不启用） | 空 |
| `LANSHARE_CHUNK_SIZE` | 分片大小（字节） | `4194304` (4MB) |
| `LANSHARE_MAX_CONCURRENT` | 并发分片数 | `3` |
| `LANSHARE_MAX_FILE_SIZE` | 单文件大小上限 | `100GB` |
| `LANSHARE_DB_POOL_SIZE` | SQLite 读连接池大小（见下文数据库池） | `5` |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | OTLP gRPC 端点（空=不启用 tracing） | 空 |
| `OTEL_TRACES_SAMPLER_PROBABILITY` | 采样率 0.0–1.0，生产建议 0.1 | `0.1` |
| `OTEL_SERVICE_NAME` | OTEL 服务名（覆盖默认 `lanshare`） | `lanshare` |
| `OTEL_SERVICE_VERSION` | 服务版本，注入 `service.version` | `1.0.0` |
| `DEPLOYMENT_ENV` | 部署环境，注入 `deployment.environment` | `development` |

示例：

```bash
# 基础
LANSHARE_PASSWORD=123456 python -m app.main

# 自定义池 + OTel
LANSHARE_DB_POOL_SIZE=5 OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4317 DEPLOYMENT_ENV=production python -m app.main

# .env 文件示例
cat > .env <<'EOF'
LANSHARE_PORT=8000
LANSHARE_DB_POOL_SIZE=5
OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4317
OTEL_TRACES_SAMPLER_PROBABILITY=0.1
DEPLOYMENT_ENV=production
EOF
```

## Database Pool & OTel

### 数据库连接池

`app/database.py` 的 `DatabasePool` 基于 `aiosqlite`：

- **读**：`pool_size` 个连接的 `asyncio.Queue` 并发复用（默认 `5`，由 `LANSHARE_DB_POOL_SIZE` 控制），`with db_read():` 获取/归还，避免频繁 `open/close` 导致 FD 泄漏。
- **写**：不复用读连接，每次 `BEGIN IMMEDIATE` 新连接 + 串行化事务（`async with db_write():`），避免 WAL 模式下的 `database is busy` 锁竞争；另有 `execute_write(coro_factory)` 队列化写入。
- **PRAGMA**：`journal_mode=WAL` / `busy_timeout=5000` / `synchronous=NORMAL` / `cache_size=-32768 (32MB)` / `timeout=30s`。

```bash
pip install aiosqlite          # 必装，database.py 强依赖
LANSHARE_DB_POOL_SIZE=10 python -m app.main   # 读并发更高时调大
```

### OpenTelemetry（可选，优雅降级）

`app/telemetry.py` + `app/main.py:lifespan` 在启动时初始化 OTel，无端点或依赖缺失时**不影响主流程**：

- **安装**：`pip install -r requirements.txt` 已含 `opentelemetry-*` 全套；如需最小安装，仅 `aiosqlite` 为必需，OTel 为可选（`telemetry.py` 以 `OTEL_AVAILABLE` 标志 + `try/except` 包裹 `FastAPI/Uvicorn/aiosqlite/httpx/logging` 插桩，缺包仅 warn）。
- **启用**：设置 `OTEL_EXPORTER_OTLP_ENDPOINT`（如 `http://otel-collector:4317` / `http://jaeger:4317`），`lifespan` 自动调用 `init_telemetry(service_name="lanshare", sample_rate=OTEL_TRACES_SAMPLER_PROBABILITY, deployment_env=DEPLOYMENT_ENV)`，注册 `BatchSpanProcessor(max_queue 2048/batch 512/5s)` + `TraceIdRatioBased` 采样 + `Resource(service.name/version/env)`。
- **关闭**：`OTEL_EXPORTER_OTLP_ENDPOINT` 留空则仅初始化 `TracerProvider` 不导出；`shutdown_telemetry()` 于 `lifespan` 退出时调用。

```bash
# 不启用 OTel（默认）
python -m app.main

# 启用并对接 Collector/Jaeger
OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4317 OTEL_TRACES_SAMPLER_PROBABILITY=0.1 DEPLOYMENT_ENV=production python -m app.main

# 仅安装核心依赖（无 OTel）
pip install fastapi "uvicorn[standard]" python-multipart aiosqlite
# 完整（含 OTel）
pip install -r requirements.txt
```

### 临时目录自动清理

`app/main.py` 的 `_cleanup_stale_temp_dirs` + `_periodic_temp_cleanup`：

- **启动时**清理 `data/tmp/` 下 `mtime > 24h` 的分片残留目录。
- **每小时**后台任务再扫一次（`asyncio.create_task`，`CancelledError` 优雅退出）。
- 正常合并完成后分片目录已删除，此为异常中断/崩溃后的兜底。

## 目录结构

```
lanshare/
├── app/                  # 后端 FastAPI
│   ├── main.py           # 入口
│   ├── config.py         # 配置
│   ├── database.py       # SQLite
│   ├── utils.py          # 路径安全/MD5
│   ├── routers/          # API 路由
│   └── services/         # 业务逻辑
├── frontend/             # 前端 Vue3
│   └── dist/             # 构建产物（后端自动托管）
├── data/
│   ├── files/            # 正式文件存储（备份此目录）
│   └── tmp/              # 分片临时目录
└── requirements.txt
```

## 备份

备份 `data/files` 目录 + `data/lanshare.db` 即可完整备份所有数据。

## 开发模式

```bash
# 终端1：启动后端
python -m app.main

# 终端2：启动前端热重载（Vite 代理 /api 到 8000 端口）
cd frontend && npm run dev
```

访问 `http://localhost:5173` 即可进入开发模式。

## API 概览

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/files?path=` | 文件列表 |
| GET | `/api/files/search` | 搜索 |
| POST | `/api/dir` | 新建文件夹 |
| DELETE | `/api/file?path=` | 删除 |
| POST | `/api/file/rename` | 重命名 |
| POST | `/api/file/move` | 移动文件/目录 |
| POST | `/api/file/copy` | 复制文件/目录 |
| POST | `/api/files/batch-delete` | 批量删除 |
| GET | `/api/file/info?path=` | 文件详情（含可预览性） |
| GET | `/api/thumbnail?path=` | 图片缩略图 |
| POST | `/api/upload/init` | 上传初始化（秒传判断） |
| POST | `/api/upload/chunk` | 上传分片 |
| GET | `/api/upload/status` | 查询已传分片 |
| POST | `/api/upload/merge` | 合并分片 |
| POST | `/api/upload/cancel` | 取消上传 |
| GET | `/api/upload/tasks` | 未完成上传任务（刷新续传） |
| GET | `/api/download?path=` | 下载（支持 Range，`?token=` 兼容浏览器直链） |
| GET | `/api/download/zip?paths=` | ZIP 打包下载 |
| GET | `/api/storage` | 存储空间（含类型分布） |
| GET | `/api/meta/network` | 局域网地址 |
| POST | `/api/auth/verify` | 密码换 token |
| GET | `/api/auth/status` | 是否启用密码 |
| POST | `/api/auth/logout` | 吊销 token |

## 测试

```bash
pip install pytest httpx
pytest tests/ -v
```

## 许可证

MIT
