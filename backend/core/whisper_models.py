"""Whisper 模型配置：按平台（Mac MLX / Windows·Linux faster-whisper）"""

import platform
import sys

# engine: mlx = Apple Silicon (M 系列) | faster_whisper = Windows / Linux / Intel Mac


def effective_platform() -> str:
    """区分 Apple Silicon 与 Intel Mac"""
    if sys.platform == "darwin":
        return "darwin" if platform.machine() == "arm64" else "darwin_intel"
    return sys.platform
WHISPER_MODEL_OPTIONS: list[dict] = [
    # ── Mac Apple Silicon (M 系列) ──
    {
        "id": "mlx-community/whisper-large-v3-mlx",
        "engine": "mlx",
        "platforms": ["darwin"],
        "label": "Large v3（最准确）",
        "group": "Mac · Apple Silicon (MLX)",
        "platform_hint": "M1/M2/M3/M4 推荐",
        "recommended_on": ["darwin"],
    },
    {
        "id": "mlx-community/whisper-medium-mlx",
        "engine": "mlx",
        "platforms": ["darwin"],
        "label": "Medium（均衡）",
        "group": "Mac · Apple Silicon (MLX)",
        "platform_hint": "速度与质量平衡",
        "recommended_on": [],
    },
    {
        "id": "mlx-community/whisper-small-mlx",
        "engine": "mlx",
        "platforms": ["darwin"],
        "label": "Small（最快）",
        "group": "Mac · Apple Silicon (MLX)",
        "platform_hint": "长视频预览",
        "recommended_on": [],
    },
    # ── Windows / Linux ──
    {
        "id": "large-v3",
        "engine": "faster_whisper",
        "platforms": ["win32", "linux", "darwin_intel"],
        "label": "Large v3（最准确）",
        "group": "Windows / Linux / Intel Mac (faster-whisper)",
        "platform_hint": "Win 推荐",
        "recommended_on": ["win32", "linux", "darwin_intel"],
    },
    {
        "id": "medium",
        "engine": "faster_whisper",
        "platforms": ["win32", "linux", "darwin_intel"],
        "label": "Medium（均衡）",
        "group": "Windows / Linux / Intel Mac (faster-whisper)",
        "platform_hint": "速度与质量平衡",
        "recommended_on": [],
    },
    {
        "id": "small",
        "engine": "faster_whisper",
        "platforms": ["win32", "linux", "darwin_intel"],
        "label": "Small（最快）",
        "group": "Windows / Linux / Intel Mac (faster-whisper)",
        "platform_hint": "低配机器",
        "recommended_on": [],
    },
]

WHISPER_MODEL_IDS = [m["id"] for m in WHISPER_MODEL_OPTIONS]

_PLATFORM_LABELS = {
    "darwin": "macOS · Apple Silicon (M 系列)",
    "darwin_intel": "macOS · Intel",
    "win32": "Windows",
    "linux": "Linux",
}


def current_platform() -> str:
    return effective_platform()


def platform_label() -> str:
    return _PLATFORM_LABELS.get(effective_platform(), sys.platform)


def get_model_spec(model_id: str) -> dict | None:
    for m in WHISPER_MODEL_OPTIONS:
        if m["id"] == model_id:
            return m
    return None


def get_recommended_model_id() -> str:
    plat = effective_platform()
    for m in WHISPER_MODEL_OPTIONS:
        if plat in m.get("recommended_on", []):
            return m["id"]
    for m in WHISPER_MODEL_OPTIONS:
        if plat in m["platforms"]:
            return m["id"]
    return WHISPER_MODEL_OPTIONS[0]["id"]


def list_options_for_api() -> list[dict]:
    """返回全部可选项，并标记是否适合当前平台"""
    plat = effective_platform()
    out = []
    for m in WHISPER_MODEL_OPTIONS:
        supported = plat in m["platforms"]
        out.append({
            "id": m["id"],
            "engine": m["engine"],
            "label": m["label"],
            "group": m["group"],
            "platform_hint": m["platform_hint"],
            "supported_on_current_platform": supported,
            "recommended": m["id"] == get_recommended_model_id(),
        })
    return out


def options_compatible_with_platform(model_id: str) -> bool:
    spec = get_model_spec(model_id)
    if not spec:
        return False
    return effective_platform() in spec["platforms"]
