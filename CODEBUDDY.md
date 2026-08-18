# CODEBUDDY.md This file provides guidance to CodeBuddy when working with code in this repository.

## 常用命令

**后端依赖安装**
```bash
pip install -r requirements.txt
# 国内网络可加: -i https://pypi.tuna.tsinghua.edu.cn/simple
```

**一键启动（推荐）**
```bash
python start.py
```
自动检查/安装后端依赖、前端 `dist/` 缺失时自动构建（需 Node.js）、检查端口占用、打印局域网地址后启动服务，Ctrl+C 优雅退出。Windows 双击 `启动.bat`（薄壳入口）即可。

**npm 工作流入口（可选，开发者习惯）**：根 `package.json` 提供与前端一致的 npm 命令，等价转发到 Python 启动器/脚本：
- `npm run dev`：`concurrently` 并行起后端（8000）+ 前端 Vite（5173 热重载）
- `npm run dev:backend` / `npm run dev:web`：单独起后端 / 前端
- `npm run start`：等价 `python start.py`
- `npm run build`：等价 `cd frontend && npm run build`
- `npm run install:all`：一键装后端 + 前端依赖
> 注意：npm 入口面向开发者；普通用户仍走 `启动.bat`，不强制安装 Node。

**手动启动后端（生产，同时托管已构建的前端）**
```bash
python -m app.main
```
监听 `0.0.0.0:8000`，终端打印局域网地址。前端 `frontend/dist/` 存在时自动托管。

**开发模式（热重载）**
```bash
# 终端1：后端
python -m app.main
# 终端2：前端 Vite 热重载（/api 代理到 8000）
cd frontend && npm install && npm run dev
# 打开 http://localhost:5173
```

**构建前端**（后端上线前必须执行，产物输出到 `frontend/dist/`）
```bash
cd frontend && npm run build
```

**打包成独立 exe**（分发给他人零依赖使用）
```bash
# 方式1（推荐）：双击「打包.bat」
# 方式2：
python -m PyInstaller LanShare.spec --noconfirm   # 产物: dist/LanShare.exe
# 改了前端代码需重建: 打包.bat rebuild
```
打包要点：入口 `launcher.py`（frozen 环境启动）；`LanShare.spec` 内嵌 `frontend/dist` → `frontend_dist`（对应 `config.IS_FROZEN` 分支 `_MEIPASS/frontend_dist`）；数据目录在 exe 旁的 `data/`。

**运行全部测试**
```bash
pip install pytest httpx
pytest tests/ -v
```
共 20 项，覆盖分片上传/秒传/断点续传/下载 Range（含并发分片拼装）/ZIP 打包（含流式完整性与目录层级）/路径穿越防护/存储统计缓存失效。

**运行单个测试**
```bash
pytest tests/test_api.py::test_resume_upload -v
```

**常用环境变量**（Windows 用 `set VAR=...`，macOS/Linux 用 `export`）
| 变量 | 默认值 |
| --- | --- |
| `LANSHARE_PORT` | `8000` |
| `LANSHARE_DATA_DIR` | `./data` |
| `LANSHARE_PASSWORD` | 空（不启用） |
| `LANSHARE_CHUNK_SIZE` | `4194304` (4MB) |
| `LANSHARE_MAX_FILE_SIZE` | `100GB` |

Windows 一键脚本：双击 `启动.bat`（部署）或 `开发模式.bat`（开发）。

## 架构概览

LanShare 是局域网文件共享工具：FastAPI 后端 + Vue3 单页前端，无外网依赖。数据存储全部在本地 `data/` 目录：正式文件在 `data/files/`，上传分片临时存放于 `data/tmp/`，元数据在 SQLite `data/lanshare.db`。备份 = 拷贝 `data/files/` + `data/lanshare.db`。

### 后端分层（app/）

清晰的三层结构，新增接口遵循该模式：
- **路由层** `app/routers/`：`files.py`、`upload.py`、`download.py`、`auth.py`。只做 HTTP 参数解析与错误映射，通过 `_handle()` 把 service 层的 `FileError`/`UploadError` 转为 400 `HTTPException`。
- **业务层** `app/services/`：`file_service.py`（列表/删除/重命名/建目录/搜索/存储统计）、`upload_service.py`（分片上传核心）、`download_service.py`（流式下载/ZIP 打包）。
- **基础层**：`config.py`（全部配置经环境变量读取，支持 PyInstaller `IS_FROZEN` 打包模式）、`database.py`（SQLite WAL 连接 + `db()` 上下文管理器自动提交/回滚 + `init_db()` 建表）、`utils.py`（路径安全、MD5、文件名清洗）。

`app/main.py` 是组装点：lifespan 里调 `ensure_dirs()` + `init_db()`；一个 HTTP 中间件保护全部 `/api/*` 路径（`/api/auth/*` 除外），未带有效 token 返回 401；还挂载了 `SelectiveGZipMiddleware`（仅压缩 text/json 响应，不影响大文件下载与 ZIP 流式）；随后把 `frontend/dist/` 挂载为静态资源，并加 SPA 回退路由（非 `/api` 路径一律返回 `index.html`）。

### 关键设计

**路径安全（安全核心）**：所有用户传入的相对路径必须经过 `utils.safe_join()` —— 拒绝绝对路径与 `..` 穿越，解析后必须落在 `FILES_DIR` 内；文件名经 `utils.sanitize_filename()` 清洗非法字符并防止以 `.` 开头。路径穿越是测试重点。

**分片上传 / 断点续传 / 秒传**（前后端协作最复杂的部分）：
1. `POST /api/upload/init` 传 `md5 + fileName + totalSize`。后端先查 `upload_tasks` 表：若存在同 md5+文件名且 status='done' 的任务且磁盘文件 md5 一致 → 秒传返回 `needUpload:false`；否则创建/复用任务，返回已上传分片索引 `uploadedChunks`。
2. `POST /api/upload/chunk` 每次一片（默认 4MB），逐片校验 chunkMd5，写 `data/tmp/<uuid>/<index>.chunk`，并将索引写入 `uploaded_chunks` JSON 字段。
3. `POST /api/upload/merge` 检查分片齐全后按序拼文件，**整体重算 MD5 校验**，失败则删文件并标记 status='failed'；同名文件自动加 ` (1)` 序号。
- 前端对应 `frontend/src/utils/md5.js`（时间切片算全文件 MD5，避免卡 UI）和 `utils/uploader.js`（并发 3 片上传池、断点续传、秒传）。前端上传引擎的进度/重试逻辑与后端 `upload_tasks` 记录共同保证可恢复。

**下载**：单文件用 FastAPI `FileResponse`，原生支持 HTTP Range（断点续传，206）。前端 `utils/downloader.js` 用 `fetch + Range` 并发分片下载（默认 4 连接，>2GB 或 <1MB 或能力不支持时自动回退跳转下载），支持进度/速度回调、暂停/继续（`AbortController`）、单分片失败重试；`App.vue` 右下角有悬浮下载面板。ZIP 打包改为流式：`download_service.iter_zip_stream()` 后台线程写磁盘临时 ZIP（`ZIP_STORED` 不压缩），主生成器边写边读增量发出（`StreamingResponse`），首字节无需等待打包完成，异常/中断时 finally 清理临时文件。中文文件名通过 `filename*=UTF-8''` 编码。

**访问密码**：仅内存 token（`auth.py` 的 `_ACTIVE_TOKENS` 集合），`POST /api/auth/verify` 用 `secrets.compare_digest` 校验密码后签发 token，前端存 localStorage 并通过 `X-Auth-Token` 头携带。**重启后端 token 全部失效**（家用场景可接受）。注意下载链接带 token 需走 query 参数（`api/index.js` 的 `withToken()`），因为浏览器 `<a>` 下载无法自定义请求头。

**数据库**：无 ORM、无迁移工具。`database.init_db()` 建 `upload_tasks` 单表，schema 变更需手工同步改建表脚本。连接走 WAL + `busy_timeout`，单文件读多写少场景足够。

**存储统计缓存**：`file_service.storage_info()` 进程内 TTL 缓存（默认 30s），大目录避免每次全量 `rglob`；上传 merge/删除/重命名/建目录成功后通过 `_invalidate_storage_cache()` 主动失效，接口返回 `cache: true/false` 供前端感知。

### 前端（frontend/）

Vue 3 + Vite + Element Plus 单页应用，无路由库拆分页面（`vue-router` 在依赖里但主界面只有 `App.vue` 一个挂载点 + `components/UploadPanel.vue` 上传面板）。`src/api/index.js` 统一封装 fetch：自动带 token、401 时派发 `lanshare-auth-fail` 事件触发密码页。全局图标通过 `main.js` 逐个注册。

开发联调关键点：Vite 开发服务器（5173）把 `/api` 代理到 8000，所以前端开发时后端必须同时在跑；改后端代码需重启后端（无 `--reload`），改前端代码 Vite 热更新即时生效。

**`vite.config.js` 中 `emptyOutDir: false` 是刻意设置**（避免构建时清空 dist 报错），不要随意改回。

### 测试（tests/test_api.py）

用 FastAPI `TestClient`。文件顶部通过 `tempfile.mkdtemp` + 设置 `os.environ["LANSHARE_DATA_DIR"]` 隔离测试数据，`sys.path.insert` 后 import `app.main`，并**手动调用 `init_db()`**（TestClient 默认不触发 lifespan）。新增 API 时遵循同样模式：独立临时数据目录、`upload_via_chunks()` 辅助函数模拟完整分片流程。

### 部署与迁移

生产部署只需 Python 3.10+：`pip install -r requirements.txt && python -m app.main`（需先 `npm run build` 出前端产物）。Node.js 18+ 仅前端构建/开发需要。`启动.bat` 一键完成依赖检查安装与启动。详见 `开发指南.md` 与 `迁移指南.md`。
