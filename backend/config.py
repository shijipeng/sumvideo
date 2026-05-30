"""SumVideo 配置文件"""

import os

# DeepSeek API 配置（Key 由用户在 Web 设置页填写，存于 backend/.local/settings.json）
# 也可通过环境变量 DEEPSEEK_API_KEY 覆盖（可选）
# 官方文档: https://api-docs.deepseek.com （OpenAI 兼容，不要加 /v1）
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-v4-flash"

# Whisper 模型列表见 core/whisper_models.py（Mac MLX / Win·Linux faster-whisper）
from core.whisper_models import WHISPER_MODEL_IDS, WHISPER_MODEL_OPTIONS  # noqa: E402

DEEPSEEK_MODEL_OPTIONS = [
    {"id": "deepseek-v4-flash", "label": "V4 Flash（推荐，速度快）"},
    {"id": "deepseek-v4-pro", "label": "V4 Pro（更强推理，适合长总结）"},
]
DEEPSEEK_MODEL_IDS = [m["id"] for m in DEEPSEEK_MODEL_OPTIONS]

# 旧版模型名自动映射到 V4（deepseek-chat / deepseek-reasoner 将于 2026-07 停用）
DEEPSEEK_MODEL_LEGACY_MAP = {
    "deepseek-chat": "deepseek-v4-flash",
    "deepseek-reasoner": "deepseek-v4-flash",
}

# 应用配置（目录由 core.paths 解析，app 启动时 init_data_paths）
def _dir(name: str) -> str:
    from core.paths import audio_dir, upload_dir

    return str(audio_dir() if name == "audio" else upload_dir())


UPLOAD_DIR = "uploads"
AUDIO_DIR = "audio"


def refresh_path_config() -> None:
    """init_data_paths 之后刷新模块级路径字符串。"""
    global UPLOAD_DIR, AUDIO_DIR
    UPLOAD_DIR = _dir("upload")
    AUDIO_DIR = _dir("audio")


HOST = os.environ.get("SUMVIDEO_BACKEND_HOST", "127.0.0.1")
PORT = int(os.environ.get("SUMVIDEO_BACKEND_PORT", "8000"))

# 超过该小时数仍为 pending/processing 的任务视为僵尸，启动时标记失败并删视频文件
STALE_TASK_HOURS = 48
# processing 超过该分钟数无更新 → 视为被 reload/崩溃打断（88% 假死）
STALE_PROCESSING_MINUTES = 15
# DeepSeek 笔记阶段 asyncio 兜底超时（应略大于 summarizer 内 httpx 总超时）
NOTES_STAGE_TIMEOUT_SEC = 360
