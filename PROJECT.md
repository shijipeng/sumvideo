# SumVideo — 项目说明与技术选型

本地 AI 视频笔记工具：本地上传或在线 URL 导入 → Whisper 转写（有字幕则跳过）→ DeepSeek 生成结构化笔记 → 可点击跳转播放、思维导图、导出 Markdown。

---

## 1. 项目定位

| 项 | 说明 |
|----|------|
| **形态** | 本机运行的 Web 应用（浏览器 + 本地后端） |
| **隐私** | 视频与转写在本机处理；仅总结阶段调用 DeepSeek API |
| **典型用户** | 学习/复盘长视频，需要带时间轴的章节笔记与导图 |
| **非目标** | Cookie 登录态、多用户 SaaS、移动端 App（当前未做） |

---

## 2. 功能清单

- **上传与处理**：支持常见视频格式；SHA256 去重；重复时可「使用已有结果」或「重新处理」
- **在线 URL 导入**：粘贴链接 → yt-dlp 拉字幕 + 下载到 `uploads/`；有合格 CC 字幕则跳过 Whisper；URL 级查重
- **转写**：本地 Whisper（Mac M 系 MLX / 其它平台 faster-whisper）；无在线字幕时 fallback
- **笔记（方案 B）**：一次 LLM 调用生成 `overview` + 多段 `sections`（含 `title`、`start_time`、`lead`、`points`）
- **转写句段**：`transcript_segments` 按章节分组展示，点击跳转
- **播放**：原生 `<video>`；章节标题行跳转；方向键快进/倍速；处理完成后可流式播放 `GET /api/video/{id}`
- **思维导图**：由笔记转 Markdown 大纲，Markmap 渲染；**不额外调用 API**；点击节点跳转对应时间
- **历史**：SQLite 记录；同文件哈希列表去重展示；强制重传会替换旧记录
- **导出**：笔记 Markdown、思维导图 Markdown
- **主题**：GitHub 风浅色/深色；侧栏可收起；上视频下笔记布局

---

## 3. 系统架构

```
┌─────────────────────────────────────────────────────────────┐
│  浏览器  http://localhost:5173                               │
│  React · Vite · Tailwind                                    │
│  VideoPlayer · NotesView · MindMapView · HistoryPanel         │
└───────────────────────────┬─────────────────────────────────┘
                            │ /api → proxy → :8000
┌───────────────────────────▼─────────────────────────────────┐
│  FastAPI  backend/  (127.0.0.1:8000)                        │
│  upload · status · history · stream · settings · retry        │
└───────┬─────────────────────────────┬───────────────────────┘
        │                             │
        ▼                             ▼
┌───────────────┐              ┌──────────────────┐
│ SQLite        │              │ 处理流水线          │
│ sumvideo.db   │              │ ffmpeg → Whisper   │
│ uploads/      │              │ → DeepSeek 笔记    │
└───────────────┘              └──────────────────┘
```

**单视频处理流程（本地上传）**

1. 上传 → 存 `uploads/{id}.ext`，写入 DB（`pending`）
2. `ffmpeg` 提取 16kHz 单声道 WAV
3. 本地 Whisper 转写 → `transcript` + `transcript_segments`
4. DeepSeek `generate_notes()` → `summary`(overview) + `chapters`(sections)
5. 状态 `done`，前端轮询 `/api/status/{id}` 展示结果

**在线 URL 导入流程**

1. `POST /api/import-url` → 写入 DB（`source_url`、占位 `file_hash`）→ 立即返回 `task_id`
2. 后台：yt-dlp 拉字幕（progress &lt; 8）→ 下载视频到 `uploads/`（8–20）
3. 有合格字幕 → 直接 DeepSeek 笔记；否则 Whisper + 笔记
4. 播放仍走 `GET /api/video/{id}`

**每个视频 API 调用次数**：Whisper 本地 0 次计费；DeepSeek **1 次**（仅笔记生成）。

---

## 4. 目录结构

```
sumvideo/
├── PROJECT.md              # 本文档（说明 + 技术选型）
├── README.md               # 快速启动摘要
├── scripts/
│   ├── start-backend.sh
│   └── start-frontend.sh
├── backend/
│   ├── app.py              # FastAPI 路由与 process_video
│   ├── config.py           # DeepSeek URL、目录、模型列表
│   ├── requirements.txt
│   ├── core/
│   │   ├── transcriber.py  # ffmpeg + MLX / faster-whisper
│   │   ├── url_importer.py # 在线 URL 校验、probe、下载
│   │   ├── subtitle_fetcher.py # yt-dlp 字幕拉取与解析
│   │   ├── summarizer.py   # DeepSeek 结构化笔记
│   │   ├── whisper_models.py
│   │   ├── settings_store.py
│   │   ├── model_download.py
│   │   └── hf_cache.py
│   ├── db/database.py      # SQLite
│   ├── uploads/            # 视频文件（gitignore）
│   ├── models/             # Hugging Face 模型缓存（gitignore）
│   └── .local/settings.json # API Key 等（gitignore, 600）
└── web/
    ├── src/
    │   ├── App.tsx
    │   ├── components/     # VideoPlayer, NotesView, MindMapView, …
    │   ├── hooks/useTaskPolling.ts
    │   └── lib/            # api, mindmapMarkdown, transcript, noteText
    ├── package.json
    └── vite.config.ts      # /api 代理到 8000
```

---

## 5. 技术选型

### 5.1 总览

| 层级 | 选型 | 版本（约） | 选型理由 |
|------|------|------------|----------|
| 前端框架 | React | 19 | 组件化、生态成熟 |
| 构建 | Vite | 5 | 开发快、与 React 配合好 |
| 样式 | Tailwind CSS | 4 | 实用类、主题变量易做 light/dark |
| 后端 | FastAPI + Uvicorn | 0.115+ | 异步友好、上传/轮询简单 |
| 数据库 | SQLite | 内置 | 零运维、单机足够 |
| 语音转写 | MLX Whisper / faster-whisper | — | **本地、免费、隐私**；按平台自动选型 |
| 文本总结 | DeepSeek API（OpenAI SDK 兼容） | V4 Flash/Pro | 便宜、中文好、一次 JSON 结构化输出 |
| 思维导图 | markmap-lib + markmap-view | 0.18 | 由 Markdown 生成 SVG，无额外 LLM |
| 播放器 | 原生 video + 自研快捷键 | — | 轻量；避免重型播放器依赖 |

### 5.2 为何本地 Whisper，不用云端 ASR？

| 维度 | 本地（当前） | 云端 Whisper API |
|------|--------------|------------------|
| 费用 | 模型下载后按分钟 **≈0 元** | 约 **$0.003～0.006/分钟** |
| 隐私 | 音频不出本机 | 需上传音频 |
| 长视频 | 无 25MB 等 API 限制 | 需分片、多次请求 |
| 速度 | M 系 Mac + MLX 通常快于实时 | 弱机可能更快，强机+长片未必 |
| 复杂度 | 需下载模型、占磁盘 | 仅需 API Key |

**结论**：个人本地工具优先本地转写；云端适合无 GPU 或极简部署，本项目未接入。

### 5.3 为何 DeepSeek 一次生成「方案 B」笔记？

- **方案 B**：单次调用返回 `{ overview, sections[] }`，每段带 `start_time` / `points`，便于章节跳转与导图。
- 避免「先分段再每段总结」多次调用，**降低成本与延迟**。
- 提示词要求 4～8 个大块、去掉「总/分」等前缀（前后端 `stripNoteLabel` 双保险）。

默认模型：`deepseek-v4-flash`（速度）；可选 `deepseek-v4-pro`（长文本推理）。

### 5.4 为何思维导图不调用 API？

- 笔记已含层级与时间信息；`buildMindmapMarkdown()` 转为 Markmap 用 Markdown。
- 节点内嵌 `data-sv-seek` / `data-sv-section`，点击通过 `data-path` 解析并 `seekTo`。
- 与「笔记 | 思维导图」Tab 切换共用同一份 `sections` 数据。

### 5.5 平台与 Whisper 引擎

| 平台 | 引擎 | 示例模型 ID |
|------|------|-------------|
| macOS Apple Silicon | `mlx_whisper` | 默认 `mlx-community/whisper-medium-mlx`；可选 large / small |
| Windows / Linux / Intel Mac | `faster_whisper` | 默认 `medium`；可选 large-v3 / small |

模型缓存目录：用户数据目录 `models/`（环境变量 `SUMVIDEO_DATA_DIR`；Web 开发默认 `backend/models/`），不写入用户全局 `~/.cache`。

桌面端（Electron）见 [DESKTOP.md](./DESKTOP.md)：与 Web 统一走 `POST /api/upload` 写入 `uploads/`，播放走 `/api/video/{id}`。

### 5.6 前端其它选型说明

- **轮询**：`useTaskPolling` 查 `/api/status/{id}`（长任务简单可靠；未用 WebSocket）。
- **Plyr**：依赖在 `package.json` 中，播放器以原生 video 为主。
- **CORS / 代理**：开发态 Vite 将 `/api` 代理到 `127.0.0.1:8000`，上传 `timeout: 0`。

### 5.7 未采用的技术（记录决策）

| 方案 | 未采用原因 |
|------|------------|
| Next.js / SSR | 纯本地工具，无需 SEO |
| PostgreSQL | 单机 SQLite 足够 |
| 云端 Whisper | 成本与隐私；见 5.2 |
| 导图二次 LLM | 笔记已够用，省 API |
| 处理完长期保留视频 | 仅 `done` 任务保留文件供历史播放；失败/重复/孤儿见存储清理 |

---

## 6. 数据模型（核心字段）

**`videos` 表（SQLite）**

| 字段 | 说明 |
|------|------|
| `id` | 任务 UUID |
| `filename` | 原始文件名 |
| `file_hash` | SHA256，用于去重 |
| `status` | `pending` / `processing` / `done` / `error` |
| `progress` | 0–100 |
| `transcript` | 全文；失败时可能存错误信息 |
| `transcript_segments` | JSON：`[{ start_time, end_time, text }]` |
| `summary` | 概述（overview） |
| `chapters` | JSON：`NoteSection[]` |

**`NoteSection`（前端 `types.ts`）**

```ts
{
  title: string
  start_time: number
  end_time: number
  lead?: string
  points?: string[]
}
```

**去重策略**

- 上传：同 `file_hash` 且已完成 → 返回 `duplicate`，由用户选择。
- `force=true`：删除同哈希旧记录与文件后再插入新任务。
- 历史列表：按 `file_hash` 只展示最新一条；启动时清理库内重复行。

---

## 7. 安装与启动

### 7.1 前置依赖

| 依赖 | 用途 |
|------|------|
| Python 3.10+ | 后端 |
| Node.js 20+ | 前端 |
| ffmpeg / ffprobe | 抽音频、时长 |

### 7.2 首次安装

```bash
# 后端
cd sumvideo/backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# 前端
cd sumvideo/web
npm install
```

### 7.3 日常启动

在 `sumvideo/` 根目录：

```bash
npm run backend   # http://127.0.0.1:8000
npm run frontend  # http://localhost:5173
```

生产构建前端：`cd web && npm run build`，再由静态服务器或反向代理提供；API 仍指向本机 8000。

### 7.4 首次使用流程

1. 打开 http://localhost:5173 → **设置页**：填写 DeepSeek API Key、选择 Whisper 与总结模型。
2. **模型下载页**：下载所选 Whisper 权重（默认 hf-mirror，Mac ARM 可走官方 Hugging Face）。
3. 主界面：上传视频 → 等待进度 → 查看笔记 / 思维导图 / 导出。

配置路径：`backend/.local/settings.json`（权限 600，不进 Git）。  
可选环境变量：`DEEPSEEK_API_KEY`、`WHISPER_MODEL`、`HF_ENDPOINT`。

---

## 8. 使用说明

1. **上传**：顶栏选择本地视频；浏览器可即时预览（blob URL），同时上传后端。
2. **重复视频**：弹窗可选「使用已有结果」或「重新处理」（复用原任务 ID，不新增历史条）。
3. **笔记**：仅**章节标题行**点击跳转；正文可选中复制；转写句段按章分组可点。
4. **思维导图**：切换 Tab；点击节点跳转视频；圆点折叠子节点。
5. **播放**：`→` 短按 +10s；长按约 0.35s 二倍速；处理完成后用服务端流播放。
6. **历史**：左侧列表，可排序、删除；同文件只显示一条最新记录。
7. **重新处理**：错误栏「重新处理」或已完成时「强制重新处理」（有 `taskId` 时走 retry，不重复建任务）。

---

## 9. HTTP API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/settings` | 读取配置、模型列表、下载状态 |
| POST | `/api/settings` | 保存 Key 与模型 |
| DELETE | `/api/settings` | 清除配置 |
| POST | `/api/upload?force=false` | 上传；`force=true` 替换同哈希旧任务 |
| POST | `/api/import-url` | 在线 URL 导入；`force=true` 替换同 URL 旧任务 |
| GET | `/api/status/{id}` | 进度与结果 |
| GET | `/api/video/{id}` | 视频流（处理后仍保留在 uploads） |
| GET | `/api/history` | 历史（按 file_hash 去重展示） |
| DELETE | `/api/history/{id}` | 删除记录与文件 |
| POST | `/api/retry/{id}` | 在原任务上重新转写+总结 |
| POST | `/api/models/download` | 触发 Whisper 模型下载 |
| GET | `/api/models/download/status` | 下载进度 |

---

## 10. 费用与性能（参考）

**DeepSeek（笔记）**：按 token 计费，约 **每个视频 1 次** 请求；与视频时长非线性，通常远低于转写时长 × 分钟单价。

**本地 Whisper**：无按分钟 API 费；耗电与耗时取决于模型（Large 最准最慢，Small 最快）。

**云端 ASR 对比（若未来扩展）**：OpenAI 系约 $0.003～0.006/分钟，适合无 GPU 机器，本项目默认不走此路径。

---

## 11. 视频文件清理（`uploads/`）

成功任务（`status=done`）**保留**视频，供历史播放与 retry。以下情况会自动删**视频文件**（实现见 `backend/core/storage_cleanup.py`）：

| 场景 | 行为 |
|------|------|
| 处理失败（转写/笔记报错） | 立即删视频，DB 保留 error 供查看/删历史 |
| 用户删除历史 | 删视频 + 删 DB 记录 |
| 同文件哈希重复任务 | 只保留最新一条，旧任务记录与文件一并删 |
| 强制重传 `force=true` | 上传前删掉同哈希旧任务与文件 |
| 僵尸任务（pending/processing 超过 48h） | 标为 error 并删视频（`config.STALE_TASK_HOURS`） |
| 孤儿文件 / `temp_*` | 启动时扫描：无 DB 记录或上传中断的临时文件 |

每次**后端启动**会执行全套清理。失败后「重新处理」需视频仍在磁盘；若文件已删，需重新上传。

---

## 12. 已知限制

- 处理长视频时后端占用高，期间其它 API 可能变慢；状态轮询有超时配置。
- 旧任务无 `transcript_segments` 需重新处理才有分段转写。
- 仅支持本地上传，不支持直接粘贴 B 站/YouTube 链接。
- Whisper 与 DeepSeek 需用户自行准备网络与 API 额度。
- 思维导图依赖 Markmap 对 HTML 节点的解析，极长笔记可能渲染较慢。

---

## 13. 扩展方向（未实现，供参考）

若做「在线视频总结 + 浏览器插件」，建议：

- **字幕优先**（YouTube 等），无字幕再用云端 ASR；
- 插件：Manifest V3 + React + Side Panel + Markmap；
- 后端可选：仅代理 DeepSeek，与 SumVideo 共用笔记 JSON 结构。

详见对话中的插件选型讨论；当前仓库 **不包含** 插件代码。

---

## 14. 关键源码索引

| 功能 | 路径 |
|------|------|
| 处理主流程 | `backend/app.py` → `process_video` |
| 转写 | `backend/core/transcriber.py` |
| 笔记生成 | `backend/core/summarizer.py` |
| 数据库 / 去重 | `backend/db/database.py` |
| 视频文件清理 | `backend/core/storage_cleanup.py` |
| 主界面 | `web/src/App.tsx` |
| 播放器 | `web/src/components/VideoPlayer.tsx` |
| 笔记 UI | `web/src/components/NotesView.tsx` |
| 思维导图 | `web/src/components/MindMapView.tsx` |
| 导图 Markdown | `web/src/lib/mindmapMarkdown.ts` |
| API 客户端 | `web/src/lib/api.ts` |

---

## 15. 版本与维护说明

本项目按当前功能 **封版维护**：以本地视频笔记 + 思维导图为核心，不计划强制追加在线爬取或多租户等能力。  
问题修复与小改进可继续基于本文档中的架构边界进行。

*文档随仓库代码更新；若与实现不一致，以代码为准。*
