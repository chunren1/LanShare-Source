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

通过环境变量配置（Windows 用 `set`，macOS/Linux 用 `export`）：

| 变量 | 说明 | 默认值 |
| --- | --- | --- |
| `LANSHARE_PORT` | 服务端口 | `8000` |
| `LANSHARE_DATA_DIR` | 数据存储目录 | `./data` |
| `LANSHARE_PASSWORD` | 访问密码（空=不启用） | 空 |
| `LANSHARE_CHUNK_SIZE` | 分片大小（字节） | `4194304` (4MB) |
| `LANSHARE_MAX_CONCURRENT` | 并发分片数 | `3` |
| `LANSHARE_MAX_FILE_SIZE` | 单文件大小上限 | `100GB` |

示例（设置访问密码）：

```bash
LANSHARE_PASSWORD=123456 python -m app.main
```

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
| POST | `/api/upload/init` | 上传初始化（秒传判断） |
| POST | `/api/upload/chunk` | 上传分片 |
| GET | `/api/upload/status` | 查询已传分片 |
| POST | `/api/upload/merge` | 合并分片 |
| GET | `/api/download?path=` | 下载（支持 Range） |
| GET | `/api/download/zip?paths=` | ZIP 打包下载 |
| GET | `/api/storage` | 存储空间 |
| GET | `/api/meta/network` | 局域网地址 |

## 测试

```bash
pip install pytest httpx
pytest tests/ -v
```

## 许可证

MIT
