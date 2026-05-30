"""用户数据目录：Web 开发默认 backend/，桌面通过 SUMVIDEO_DATA_DIR 注入。"""

from __future__ import annotations

import os
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent

_data_dir: Path | None = None


def get_data_dir() -> Path:
    if _data_dir is not None:
        return _data_dir
    env = os.environ.get("SUMVIDEO_DATA_DIR", "").strip()
    if env:
        return Path(env).expanduser().resolve()
    return BACKEND_DIR


def init_data_paths() -> Path:
    """创建数据目录子路径；须在 hf_cache、database 使用前调用。"""
    global _data_dir
    root = get_data_dir()
    _data_dir = root
    for name in ("uploads", "audio", "models"):
        (root / name).mkdir(parents=True, exist_ok=True)
    return root


def db_path() -> Path:
    return get_data_dir() / "sumvideo.db"


def settings_path() -> Path:
    return get_data_dir() / "settings.json"


def models_dir() -> Path:
    return get_data_dir() / "models"


def upload_dir() -> Path:
    return get_data_dir() / "uploads"


def audio_dir() -> Path:
    return get_data_dir() / "audio"
