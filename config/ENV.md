# SumVideo 环境配置

单一来源：`config/environments.json`。改端口时只改这一处，然后重启前后端。

## 环境对照

| | **dev**（本地开发） | **desktop**（安装版 App） |
|--|---------------------|---------------------------|
| 用途 | 浏览器 Web、`npm run desktop:dev` | `.dmg` / `.app` 安装包 |
| 前端 | http://127.0.0.1:5173（Vite） | 内嵌 `web/dist`（无 5173） |
| 后端 API | http://127.0.0.1:8000 | http://127.0.0.1:8001 |
| 数据目录 | `sumvideo/backend/` | `~/Library/Application Support/SumVideo` |
| 共用后端 | Electron 开发可复用已启动的 `npm run backend` | 独立进程，不复用 8000 |

## 常用命令

```bash
# 默认 dev
npm run backend    # → 8000
npm run frontend   # → 5173，/api 代理到 8000

npm run desktop:dev   # Electron + Vite 5173 + 后端 8000（可复用）

# 安装包由 Electron 自动走 desktop（8001），无需设 SUMVIDEO_ENV
```

## 覆盖

复制 `.env.example` 为项目根 `.env` 或在命令前导出：

```bash
export SUMVIDEO_BACKEND_PORT=9000
npm run backend
```

脚本 `scripts/load-env.sh` 会读取 `SUMVIDEO_ENV` 并导出 `SUMVIDEO_BACKEND_URL` 等变量。
