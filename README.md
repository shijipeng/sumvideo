# SumVideo

本地 AI 视频总结工具：Whisper MLX 转写 + DeepSeek 章节分析与总结。

**完整说明与技术选型见：[PROJECT.md](./PROJECT.md)**

## 目录结构

```
sumvideo/
├── backend/          # Python FastAPI（本地 8000 端口）
└── web/              # Vite + React 前端（本地 5173 端口）
```

## 前置条件（需你本机已安装）

以下**不会**由项目自动安装到系统全局，请自行确认：

| 依赖 | 用途 | 检查命令 |
|------|------|----------|
| Python 3.10+ | 后端 | `python3 --version` |
| Node.js 20+ | 前端（项目使用 Vite 5，兼容 20.17） | `node --version` |
| ffmpeg | 从视频提取音频 | `ffmpeg -version` |

> **Whisper 转写**：Mac M 系列用 **mlx-whisper**；Windows / Linux / Intel Mac 用 **faster-whisper**。模型下载到 **`backend/models/`**（已 gitignore，不会进仓库；不会写到 `~/.cache`）。

## 快速启动（联调用 dev，无需 build）

在 **`sumvideo/` 根目录** 开两个终端：

**终端 1 — 后端：**

```bash
npm run backend
```

**终端 2 — 前端：**

```bash
npm run frontend
```

浏览器打开：http://localhost:5173

（等价于 `./scripts/start-backend.sh` 与 `cd web && npm run dev`）

## 首次安装（仅第一次）

**后端**（依赖装在 `backend/.venv`，不进全局）：

```bash
cd sumvideo/backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

**前端**（依赖在 `web/node_modules`）：

```bash
cd sumvideo/web
npm install
```

> 若 `npm install` 报缓存权限错误，可加：`npm install --cache ./.npm-cache`

## 首次使用（必须先完成）

打开 http://localhost:5173 后，会先进入 **初始设置页**，必须完成：

1. 填写 **DeepSeek API Key**（客户自行在 DeepSeek 平台申请）
2. 选择 **Whisper 转写模型**（本机 MLX，首次使用会下载模型）
3. 选择 **DeepSeek 总结模型**

保存后会进入 **模型下载页**（仅针对你刚选的 Whisper 模型，可点「开始下载」；默认从 **hf-mirror.com** 下载，需官网时可设置 `HF_ENDPOINT=https://huggingface.co`）。下载完成后才进入主界面。配置保存在 `backend/.local/settings.json`（权限 600），不会进入 Git。

可选环境变量（高级用户）：`DEEPSEEK_API_KEY`、`WHISPER_MODEL`

## 使用说明

1. 完成初始设置后，选择本地视频文件
2. 浏览器本地播放视频，同时上传到后端转写
3. 等待进度条完成，查看章节与 AI 总结
4. 点击章节可跳转播放；播放时自动高亮当前章节
5. 支持导出 `summary.md`、历史记录与重复视频提示

## API

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/upload?force=true` | 上传视频 |
| GET | `/api/status/{id}` | 查询进度与结果 |
| GET | `/api/history` | 历史列表 |
| DELETE | `/api/history/{id}` | 删除记录 |
| POST | `/api/retry/{id}` | 重新处理（需视频文件仍在 uploads/） |
