"""Whisper 模型目录：固定在本项目 backend/models 下（非 .cache）"""

import os
from pathlib import Path

# backend/ 目录（与 app.py 同级）
BACKEND_DIR = Path(__file__).resolve().parent.parent
# Hugging Face Hub 本地仓库根目录（内含 models--* 文件夹）
HF_HUB_CACHE_DIR = BACKEND_DIR / "models"

# 默认镜像（faster-whisper 等）；MLX 模型权重需走官网（镜像站无完整文件）
HF_MIRROR_ENDPOINT = "https://hf-mirror.com"
HF_OFFICIAL_ENDPOINT = "https://huggingface.co"


def _is_apple_silicon() -> bool:
    import platform
    import sys

    return sys.platform == "darwin" and platform.machine() == "arm64"


def resolve_hf_endpoint(engine: str | None = None) -> str:
    """MLX 模型必须官网；其他平台默认镜像（可被 HF_ENDPOINT 覆盖）"""
    if engine == "mlx" or _is_apple_silicon():
        return HF_OFFICIAL_ENDPOINT
    return os.environ.get("HF_ENDPOINT", HF_MIRROR_ENDPOINT).rstrip("/")


def setup_hf_hub_cache() -> str:
    """创建模型目录并设置环境变量，供 huggingface_hub / mlx-whisper / faster-whisper 使用"""
    cache = str(HF_HUB_CACHE_DIR)
    HF_HUB_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    os.environ["HUGGINGFACE_HUB_CACHE"] = cache
    # 必须在 huggingface_hub 首次 import 前设好，否则 ENDPOINT 会锁死在镜像
    os.environ["HF_ENDPOINT"] = resolve_hf_endpoint()
    return cache


def get_hf_endpoint() -> str:
    return resolve_hf_endpoint()


def get_hf_hub_cache_dir() -> str:
    """返回当前生效的 HF hub 模型目录（需先调用 setup_hf_hub_cache）"""
    return os.environ.get("HUGGINGFACE_HUB_CACHE", str(HF_HUB_CACHE_DIR))
