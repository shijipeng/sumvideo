# SumVideo 桌面端

Electron 壳 + 内嵌 Python（方案 B）+ 本地 FastAPI。Web 与桌面**共用同一套上传与播放逻辑**：选视频后 `POST /api/upload` 复制到 `uploads/`，播放走 `GET /api/video/{id}`。

## 与 Web 版的区别

| 项 | Web（浏览器） | 桌面（Electron） |
|----|----------------|------------------|
| 选视频 | `<input type="file">` → 上传 | 系统文件对话框 → IPC 读文件 → 同一上传接口 |
| 存储 | `uploads/{id}.ext` | 同左 |
| 播放 | `/api/video/{id}` 或上传中 blob 预览 | 同左 |
| 数据目录 | 默认 `backend/` | 安装包：`Application Support`；**源码调试**（未打包 Electron）与 Web 共用 `backend/` |
| Python / ffmpeg | 本机自装 | 安装包内 venv + 捆绑 ffmpeg（发布构建） |

## 环境配置

端口与地址统一在 **`config/environments.json`**，说明见 **`config/ENV.md`**。

| 环境 | 前端 | 后端 API | 数据 |
|------|------|----------|------|
| **dev** | :5173 | :8000 | `backend/` |
| **desktop**（安装包） | 内嵌静态页 | :8001 | Application Support |

## 开发调试（本机已有 Python venv）

**终端 1 — 后端**：

```bash
cd sumvideo && npm run backend
```

**终端 2 — 前端**：

```bash
cd sumvideo && npm run frontend
```

**终端 3 — Electron**（需先 `npm install` 根目录依赖）：

```bash
cd sumvideo && npm run desktop:dev
```

`desktop:dev` 使用 **dev** 配置（5173 + 8000，可复用已启动的后端）。**已安装的 .app** 自动使用 **desktop** 配置（8001，独立数据目录）。

## 发布构建（概要）

1. 构建前端：`npm run build:web`
2. 按平台构建 Python venv：
   - macOS ARM: `bash scripts/build-python-venv.sh` → `dist/venv-darwin-arm64`
   - Windows: `powershell scripts/build-python-venv.ps1` → `dist/venv-win32`
3. 将 **ffmpeg** 放入 `electron/resources/bin/darwin-arm64/ffmpeg`（及 Win 对应路径），再打安装包
4. `npm run desktop:build`（mac arm64；等同 `desktop:build:mac`）

**不会**把 `backend/models`、上传缓存、数据库打进安装包；Whisper 权重在用户首次使用时下载到 `Application Support/SumVideo/models`。

安装包输出目录：`dist/desktop/`（仅保留 **`.dmg` / `.zip`**；打包脚本会在生成安装包后自动删除中间的 `mac/SumVideo.app` 目录）。

## 环境变量

| 变量 | 说明 |
|------|------|
| `SUMVIDEO_DATA_DIR` | 用户数据根目录（DB、settings、models、audio、uploads） |
| `SUMVIDEO_FFMPEG` | ffmpeg 可执行文件路径 |
| `SUMVIDEO_PYTHON` | 覆盖桌面端使用的 Python 解释器 |
| `SUMVIDEO_DEV=1` | Electron 加载 Vite 开发服务器 |
| `SUMVIDEO_API_PORT` | 后端端口（默认 8000） |

## 注意事项

- 超大视频经 IPC 读入渲染进程再上传，可能占用较多内存；后续可改为服务端复制而不改 UI。
- 旧版仅记录 `source_path` 的历史仍可播放（后端回退）；重新上传后会写入 `uploads/` 副本。
- 删除历史会删除 `uploads/` 中的副本，**不会**删除用户磁盘上的原文件（若旧记录带 `source_path`）。
