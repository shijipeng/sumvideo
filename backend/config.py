"""SumVideo 配置文件"""

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

# 应用配置
UPLOAD_DIR = "uploads"       # 上传视频临时存储目录
AUDIO_DIR = "audio"           # 提取的音频临时存储目录
HOST = "127.0.0.1"
PORT = 8000

# 超过该小时数仍为 pending/processing 的任务视为僵尸，启动时标记失败并删视频文件
STALE_TASK_HOURS = 48
