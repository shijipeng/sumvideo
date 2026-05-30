"""Whisper 模型预下载（在用户选定模型之后执行）"""

import json
import os
import shutil
import threading
import time
from pathlib import Path

from tqdm.auto import tqdm as BaseTqdm

from core.hf_cache import (
    HF_MIRROR_ENDPOINT,
    HF_OFFICIAL_ENDPOINT,
    get_hf_endpoint,
    get_hf_hub_cache_dir,
    resolve_hf_endpoint,
    setup_hf_hub_cache,
)
from core.paths import get_data_dir
from core.whisper_models import get_model_spec

setup_hf_hub_cache()

# 预估体积与下载时间说明（供前端展示）
MODEL_SIZE_HINTS: dict[str, dict] = {
    "mlx-community/whisper-small-mlx": {
        "size_gb": 0.5,
        "eta_text": "约 3–15 分钟（视网速而定）",
    },
    "mlx-community/whisper-medium-mlx": {
        "size_gb": 1.5,
        "eta_text": "约 10–30 分钟",
    },
    "mlx-community/whisper-large-v3-mlx": {
        "size_gb": 3.0,
        "eta_text": "约 20–60 分钟",
    },
    "small": {"size_gb": 0.5, "eta_text": "约 3–15 分钟"},
    "medium": {"size_gb": 1.5, "eta_text": "约 10–30 分钟"},
    "large-v3": {"size_gb": 3.0, "eta_text": "约 20–60 分钟"},
}

FASTER_WHISPER_HF_REPO = {
    "large-v3": "Systran/faster-whisper-large-v3",
    "medium": "Systran/faster-whisper-medium",
    "small": "Systran/faster-whisper-small",
}

STALL_SECONDS = 90
DOWNLOAD_PROGRESS_CAP = 95

_lock = threading.Lock()
_state = {
    "status": "idle",  # idle | downloading | done | error
    "progress": 0,
    "message": "",
    "model_id": None,
    "error": None,
    "bytes_updated_at": None,
    "started_at": None,
}
def _state_file() -> Path:
    return get_data_dir() / "download_state.json"


def _load_persisted_state() -> None:
    sf = _state_file()
    if not sf.exists():
        return
    try:
        data = json.loads(sf.read_text(encoding="utf-8"))
        with _lock:
            _state.update({k: data[k] for k in _state if k in data})
    except (OSError, json.JSONDecodeError, TypeError):
        pass


_load_persisted_state()


def _recover_stale_download_state() -> None:
    """进程重启后无下载线程，勿长期停在 downloading。"""
    with _lock:
        if _state.get("status") != "downloading":
            return
        model_id = _state.get("model_id")
    if not model_id:
        _set_state(status="idle", progress=0, message="", error=None)
        return
    with _lock:
        _state["status"] = "idle"
    if is_model_cached(model_id):
        _set_state(
            status="done",
            progress=100,
            message="模型已就绪",
            model_id=model_id,
            error=None,
        )
        return
    _set_state(
        status="error",
        progress=0,
        message="上次下载未完成",
        error="下载已中断，请重新点击「开始下载」",
        model_id=model_id,
    )


def _hf_repo_id(model_id: str, engine: str) -> str:
    if engine == "faster_whisper":
        return FASTER_WHISPER_HF_REPO.get(model_id, model_id)
    return model_id


def get_cache_dir() -> str:
    return get_hf_hub_cache_dir()


def _download_in_progress(model_id: str) -> bool:
    with _lock:
        return _state["status"] == "downloading" and _state.get("model_id") == model_id


def _expected_bytes(model_id: str) -> int:
    hint = MODEL_SIZE_HINTS.get(model_id, {})
    size_gb = hint.get("size_gb", 2.0)
    return int(size_gb * (1024**3))


def _progress_from_bytes(size: int, expected: int, *, cap: int = DOWNLOAD_PROGRESS_CAP) -> int:
    """按已下载字节线性计算进度（0–cap），避免早期虚高。"""
    if expected <= 0:
        return min(cap, 50)
    if size <= 0:
        return 0
    return min(cap, max(1, int(size * 100 / expected)))


def _is_download_stalled() -> bool:
    with _lock:
        if _state.get("status") != "downloading":
            return False
        updated_at = _state.get("bytes_updated_at") or 0
        started_at = _state.get("started_at") or 0
    ref = updated_at or started_at
    if ref <= 0:
        return False
    return time.time() - ref >= STALL_SECONDS


def _configure_hf_download_timeouts() -> None:
    os.environ.setdefault("HF_HUB_DOWNLOAD_TIMEOUT", "120")
    os.environ.setdefault("HF_HUB_ETAG_TIMEOUT", "30")


class _HubDownloadProgress(BaseTqdm):
    """把 huggingface_hub 的 tqdm 进度同步到下载状态，供前端轮询展示"""

    def __init__(self, *args, **kwargs):
        # disable=True 时 tqdm 不会设置 desc 属性，需自行保存
        self._progress_label = (kwargs.get("desc") or "下载模型文件").strip()
        kwargs.setdefault("disable", True)
        super().__init__(*args, **kwargs)
        self._sync()

    def update(self, n=1):
        result = super().update(n)
        self._sync()
        return result

    def refresh(self, *args, **kwargs):
        result = super().refresh(*args, **kwargs) if hasattr(super(), "refresh") else None
        self._sync()
        return result

    def _sync(self):
        total = getattr(self, "total", None)
        if not total or total <= 0:
            return
        label = getattr(self, "desc", None) or self._progress_label or "下载模型文件"
        if isinstance(label, str):
            label = label.strip() or "下载模型文件"
        _set_state(message=f"正在下载 {label}…")


def _monitor_cache_size(model_id: str, repo_id: str, stop_event: threading.Event):
    """按缓存目录体积估算进度（多文件下载时的补充）"""
    try:
        from huggingface_hub.file_download import repo_folder_name

        folder = Path(get_cache_dir()) / repo_folder_name(repo_id=repo_id, repo_type="model")
        expected = _expected_bytes(model_id)
        last_size = -1
        last_change = time.monotonic()
        while not stop_event.wait(1):
            if not folder.exists():
                continue
            size = _repo_bytes_on_disk(repo_id, include_incomplete=True)
            if size <= 0:
                continue
            now = time.monotonic()
            if size > last_size:
                last_size = size
                last_change = now
            elif now - last_change >= STALL_SECONDS:
                mb = size / (1024**2)
                _set_state(
                    status="error",
                    progress=_progress_from_bytes(size, expected),
                    message=f"下载停滞于 {mb:.1f} MB",
                    error=(
                        f"超过 {STALL_SECONDS} 秒无新数据。"
                        "若使用代理（如 Clash 7897），请确认 huggingface.co 可访问，"
                        "或暂时关闭系统代理后点击「开始下载」重试。"
                    ),
                    bytes_updated_at=time.time(),
                )
                return
            pct = _progress_from_bytes(size, expected)
            mb = size / (1024**2)
            total_mb = expected / (1024**2)
            _set_state(
                progress=pct,
                message=f"已写入磁盘 {mb:.1f} MB / 约 {total_mb:.0f} MB",
                bytes_updated_at=time.time(),
            )
    except Exception:
        pass


def _repo_cache_folder(repo_id: str) -> Path:
    from huggingface_hub.file_download import repo_folder_name

    return Path(get_cache_dir()) / repo_folder_name(repo_id=repo_id, repo_type="model")


def _has_incomplete_blobs(repo_id: str) -> bool:
    folder = _repo_cache_folder(repo_id)
    if not folder.exists():
        return False
    for path in folder.rglob("*"):
        if path.is_file() and ".incomplete" in path.name:
            return True
    return False


def _repo_bytes_on_disk(repo_id: str, *, include_incomplete: bool = False) -> int:
    """include_incomplete=True 时计入 .incomplete 临时文件（下载进度用）。"""
    folder = _repo_cache_folder(repo_id)
    if not folder.exists():
        return 0
    total = 0
    for path in folder.rglob("*"):
        if not path.is_file():
            continue
        if not include_incomplete and ".incomplete" in path.name:
            continue
        try:
            total += path.stat().st_size
        except OSError:
            continue
    return total


def _snapshot_has_model_files(snapshot_path: Path, engine: str) -> bool:
    """确认 snapshot 里已有可加载的权重文件，而不是只有 config/README"""
    if engine == "mlx":
        for name in ("weights.safetensors", "weights.npz"):
            weights = snapshot_path / name
            if weights.is_file() and weights.stat().st_size > 1_000_000:
                return True
        return False

    model_bin = snapshot_path / "model.bin"
    return model_bin.is_file() and model_bin.stat().st_size > 1_000_000


def is_model_cached(model_id: str) -> bool:
    """检查项目内 HF 缓存是否已有完整模型（下载中、半成品均不算就绪）"""
    if _download_in_progress(model_id):
        return False

    spec = get_model_spec(model_id)
    if not spec:
        return False

    repo_id = _hf_repo_id(model_id, spec["engine"])
    cache_dir = get_cache_dir()

    if _has_incomplete_blobs(repo_id):
        return False

    min_bytes = int(_expected_bytes(model_id) * 0.5)
    if _repo_bytes_on_disk(repo_id) < min_bytes:
        return False

    try:
        from huggingface_hub import snapshot_download

        snapshot_path = Path(
            snapshot_download(
                repo_id=repo_id,
                local_files_only=True,
                cache_dir=cache_dir,
                endpoint=resolve_hf_endpoint(spec["engine"]),
            )
        )
    except Exception:
        return False

    return _snapshot_has_model_files(snapshot_path, spec["engine"])


def get_download_hint(model_id: str) -> dict:
    hint = MODEL_SIZE_HINTS.get(model_id, {"size_gb": 2.0, "eta_text": "视网速而定"})
    spec = get_model_spec(model_id)
    return {
        "model_id": model_id,
        "label": spec["label"] if spec else model_id,
        "engine": spec["engine"] if spec else "unknown",
        "size_gb": hint["size_gb"],
        "eta_text": hint["eta_text"],
        "cache_dir": get_cache_dir(),
        "mirror_hint": _download_source_hint(spec["engine"] if spec else "unknown"),
    }


def _download_source_hint(engine: str) -> str:
    if engine == "mlx":
        return f"{HF_OFFICIAL_ENDPOINT}（MLX 模型需官网；镜像无权重文件）"
    primary = get_hf_endpoint().rstrip("/")
    if primary == HF_OFFICIAL_ENDPOINT.rstrip("/"):
        return HF_OFFICIAL_ENDPOINT
    return f"{primary}（失败时自动回退官网）"


def _download_endpoints(engine: str) -> list[tuple[str, str]]:
    """返回 (HF_ENDPOINT, 展示名) 列表，按顺序尝试"""
    official = HF_OFFICIAL_ENDPOINT.rstrip("/")
    mirror = HF_MIRROR_ENDPOINT.rstrip("/")
    if engine == "mlx":
        return [(official, "Hugging Face 官网")]
    primary = resolve_hf_endpoint(engine).rstrip("/")
    if primary == official:
        return [(official, "Hugging Face 官网")]
    if primary == mirror:
        return [(mirror, "hf-mirror 镜像"), (official, "Hugging Face 官网")]
    return [(primary, primary), (official, "Hugging Face 官网")]


def _clear_repo_cache(repo_id: str) -> None:
    folder = _repo_cache_folder(repo_id)
    if folder.exists():
        shutil.rmtree(folder, ignore_errors=True)


def _snapshot_download_repo(repo_id: str, engine: str) -> str:
    from huggingface_hub import snapshot_download

    cache_dir = get_cache_dir()
    endpoints = _download_endpoints(engine)
    last_error: Exception | None = None
    _configure_hf_download_timeouts()

    for i, (endpoint, label) in enumerate(endpoints):
        os.environ["HF_ENDPOINT"] = endpoint
        try:
            _set_state(
                progress=0,
                message=f"正在从 {label} 下载 {repo_id}…",
            )
            return snapshot_download(
                repo_id=repo_id,
                cache_dir=cache_dir,
                endpoint=endpoint,
                etag_timeout=30,
                max_workers=4,
                tqdm_class=_HubDownloadProgress,
            )
        except Exception as e:
            last_error = e
            if i < len(endpoints) - 1:
                _set_state(
                    progress=3,
                    message=f"{label} 不可用，正在切换官网…",
                )
                _clear_repo_cache(repo_id)
            continue

    raise last_error or RuntimeError("下载失败")


def _disk_progress(model_id: str) -> dict | None:
    """按缓存目录体积计算进度（含 .incomplete）。"""
    spec = get_model_spec(model_id)
    if not spec:
        return None
    repo_id = _hf_repo_id(model_id, spec["engine"])
    size = _repo_bytes_on_disk(repo_id, include_incomplete=True)
    if size <= 0:
        return None
    expected = _expected_bytes(model_id)
    pct = _progress_from_bytes(size, expected)
    mb = round(size / (1024**2), 1)
    total_mb = round(expected / (1024**2), 0)
    return {
        "progress": pct,
        "message": f"已写入磁盘 {mb} MB / 约 {int(total_mb)} MB",
        "bytes_downloaded": size,
        "bytes_total": expected,
    }


def reconcile_download_state() -> None:
    """切换 Whisper 模型后，清除与当前选择不一致或过期的 download_state。"""
    try:
        from core.settings_store import get_whisper_model, is_settings_ready

        if not is_settings_ready():
            return
        current = get_whisper_model()
    except Exception:
        return

    with _lock:
        stored_id = _state.get("model_id")
        stored_status = _state.get("status")

    if stored_id and stored_id != current:
        _set_state(
            status="idle",
            progress=0,
            message="",
            model_id=None,
            error=None,
        )
        return

    if stored_status == "done" and not is_model_cached(current):
        _set_state(
            status="idle",
            progress=0,
            message="",
            error=None,
        )


def get_download_status() -> dict:
    reconcile_download_state()
    with _lock:
        state = dict(_state)
    model_id = state.get("model_id")
    if state.get("status") == "downloading" and model_id:
        disk = _disk_progress(model_id)
        if disk:
            state["progress"] = disk["progress"]
            state["message"] = disk["message"]
            state["bytes_downloaded"] = disk["bytes_downloaded"]
            state["bytes_total"] = disk["bytes_total"]
    return state


def _set_state(**kwargs):
    with _lock:
        _state.update(kwargs)
        snapshot = dict(_state)
    try:
        sf = _state_file()
        sf.parent.mkdir(parents=True, exist_ok=True)
        sf.write_text(
            json.dumps(snapshot, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError:
        pass


def _run_download(model_id: str):
    spec = get_model_spec(model_id)
    if not spec:
        _set_state(status="error", error=f"未知模型: {model_id}", progress=0)
        return

    if is_model_cached(model_id):
        _set_state(
            status="done",
            progress=100,
            message="模型已在本地缓存",
            model_id=model_id,
            error=None,
        )
        return

    repo_id = _hf_repo_id(model_id, spec["engine"])
    stop_monitor = threading.Event()
    monitor = threading.Thread(
        target=_monitor_cache_size,
        args=(model_id, repo_id, stop_monitor),
        daemon=True,
    )
    try:
        _set_state(
            status="downloading",
            progress=0,
            message=f"正在从 Hugging Face 下载 {repo_id}…",
            model_id=model_id,
            error=None,
            started_at=time.time(),
            bytes_updated_at=time.time(),
        )
        monitor.start()
        _snapshot_download_repo(repo_id, spec["engine"])
        with _lock:
            stalled = _state.get("status") == "error"
        if stalled:
            return
        _set_state(
            status="done",
            progress=100,
            message="模型下载完成",
            model_id=model_id,
            error=None,
        )
    except Exception as e:
        _set_state(
            status="error",
            progress=0,
            message="下载失败",
            error=str(e),
            model_id=model_id,
        )
    finally:
        stop_monitor.set()
        monitor.join(timeout=1)


def start_download(model_id: str) -> bool:
    """在后台线程启动下载，若已在下载同一模型则返回 False"""
    with _lock:
        if _state["status"] == "downloading" and _state.get("model_id") == model_id:
            if not _is_download_stalled():
                return False
            _state["status"] = "idle"

    if is_model_cached(model_id):
        _set_state(
            status="done",
            progress=100,
            message="模型已就绪",
            model_id=model_id,
            error=None,
        )
        return False

    _set_state(
        status="downloading",
        progress=0,
        message="准备下载…",
        model_id=model_id,
        error=None,
    )
    thread = threading.Thread(target=_run_download, args=(model_id,), daemon=True)
    thread.start()
    return True


_recover_stale_download_state()
