"""用户本地设置（API Key、模型等），存于用户数据目录，不提交 Git"""

import json
import os
import shutil
from pathlib import Path

import config
from core.paths import BACKEND_DIR, get_data_dir, settings_path
from core.whisper_models import WHISPER_MODEL_IDS, get_recommended_model_id, options_compatible_with_platform

_LEGACY_SETTINGS = BACKEND_DIR / ".local" / "settings.json"


def _settings_file() -> Path:
    return settings_path()


def _ensure_dir():
    get_data_dir().mkdir(parents=True, exist_ok=True)


def _migrate_legacy_settings() -> None:
    target = _settings_file()
    if target.exists() or not _LEGACY_SETTINGS.is_file():
        return
    try:
        shutil.copy2(_LEGACY_SETTINGS, target)
        os.chmod(target, 0o600)
    except OSError:
        pass


def _load() -> dict:
    _migrate_legacy_settings()
    path = _settings_file()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _save(data: dict) -> None:
    _ensure_dir()
    path = _settings_file()
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def is_valid_api_key(key: str) -> bool:
    """DeepSeek API Key 应以 sk- 开头，且不是 URL 等误填内容"""
    k = (key or "").strip()
    if len(k) < 10:
        return False
    if k.startswith("http://") or k.startswith("https://"):
        return False
    return k.startswith("sk-")


def mask_api_key(key: str) -> str:
    """供前端密码框展示：已配置但不可见明文"""
    k = (key or "").strip()
    if not k:
        return ""
    if len(k) <= 7:
        return "sk-" + "•" * 8
    return f"{k[:3]}{'•' * 12}{k[-4:]}"


def get_api_key() -> str:
    env_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if env_key:
        return env_key
    return (_load().get("deepseek_api_key") or "").strip()


def get_stored_api_key_raw() -> str:
    """文件中的 Key（不校验格式，用于判断误填）"""
    return (_load().get("deepseek_api_key") or "").strip()


def get_whisper_model() -> str:
    env_model = os.environ.get("WHISPER_MODEL", "").strip()
    if env_model:
        return env_model
    saved = (_load().get("whisper_model") or "").strip()
    if saved:
        return saved
    return get_recommended_model_id()


def get_deepseek_model() -> str:
    raw = (_load().get("deepseek_model") or config.DEEPSEEK_MODEL).strip()
    return config.DEEPSEEK_MODEL_LEGACY_MAP.get(raw, raw)


def save_settings(api_key: str, whisper_model: str, deepseek_model: str) -> None:
    key = api_key.strip()
    if not is_valid_api_key(key):
        raise ValueError(
            "DeepSeek API Key 格式不正确：应以 sk- 开头，请在 https://platform.deepseek.com 获取"
        )
    data = _load()
    data["deepseek_api_key"] = key
    data["whisper_model"] = whisper_model.strip()
    data["deepseek_model"] = (deepseek_model or config.DEEPSEEK_MODEL).strip()
    _save(data)


def clear_all_settings() -> None:
    path = _settings_file()
    if path.exists():
        path.unlink(missing_ok=True)


def is_api_configured() -> bool:
    return is_valid_api_key(get_api_key())


def has_invalid_stored_api_key() -> bool:
    raw = get_stored_api_key_raw()
    return bool(raw) and not is_valid_api_key(raw)


def is_whisper_configured() -> bool:
    model = get_whisper_model()
    return model in WHISPER_MODEL_IDS and options_compatible_with_platform(model)


def is_settings_ready() -> bool:
    """API Key 与 Whisper 模型已选择并保存"""
    return is_api_configured() and is_whisper_configured()


def is_fully_ready() -> bool:
    """设置完成且当前所选 Whisper 模型已下载到本地"""
    if not is_settings_ready():
        return False
    from core.model_download import is_model_cached

    return is_model_cached(get_whisper_model())


def is_ready() -> bool:
    """进入主界面 / 上传视频的前置条件"""
    return is_fully_ready()


# 兼容旧接口名
def is_configured() -> bool:
    return is_fully_ready()
