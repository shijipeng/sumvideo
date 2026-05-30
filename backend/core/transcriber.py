"""视频转写：Mac 用 MLX Whisper，Windows/Linux 用 faster-whisper"""

import hashlib
import os
import subprocess
from pathlib import Path

from core.hf_cache import setup_hf_hub_cache
from core.paths import audio_dir
from core.whisper_models import get_model_spec

setup_hf_hub_cache()


def _ffmpeg_bin() -> str:
    return (os.environ.get("SUMVIDEO_FFMPEG") or "ffmpeg").strip() or "ffmpeg"


def _ffprobe_bin() -> str:
    ff = _ffmpeg_bin()
    if ff.endswith("ffmpeg"):
        return ff[:-6] + "ffprobe"
    return "ffprobe"


def extract_audio(video_path: str, audio_path: str) -> str:
    """用 ffmpeg 从视频中提取音频"""
    result = subprocess.run(
        [
            _ffmpeg_bin(), "-i", video_path,
            "-vn",
            "-acodec", "pcm_s16le",
            "-ar", "16000",
            "-ac", "1",
            "-y",
            audio_path,
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg 提取音频失败: {result.stderr}")
    return audio_path


def _audio_duration_seconds(audio_path: str) -> float:
    """用 ffprobe 获取音频时长，用于转写进度估算"""
    try:
        result = subprocess.run(
            [
                _ffprobe_bin(),
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                audio_path,
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0 and result.stdout.strip():
            return max(float(result.stdout.strip()), 1.0)
    except (OSError, ValueError):
        pass
    return 1.0


def _mlx_transcribe_once(
    mlx_whisper,
    audio_path: str,
    model_name: str,
    *,
    progress_callback=None,
    mlx_transcribe_mod=None,
) -> dict:
    """单次 MLX 转写；progress_callback 时通过静默 tqdm 更新 DB，不写终端。"""
    if not progress_callback or mlx_transcribe_mod is None:
        return mlx_whisper.transcribe(
            audio_path,
            path_or_hf_repo=model_name,
            verbose=False,
        )

    from tqdm.auto import tqdm as BaseTqdm

    class _MLXTranscribeProgress(BaseTqdm):
        """把 mlx_whisper 内部 tqdm（按帧）同步到任务进度，不向 stdout 画条。"""

        def __init__(self, *args, **kwargs):
            # 不向终端画进度条，避免 uvicorn/管道环境下 Broken pipe
            kwargs.setdefault("disable", True)
            self._cb = progress_callback
            super().__init__(*args, **kwargs)

        def update(self, n=1):
            try:
                result = super().update(n)
            except BrokenPipeError:
                result = None
            if self._cb and self.total and self.total > 0:
                frac = min(1.0, self.n / self.total)
                pct = 10 + int(frac * 80)
                self._cb(pct, f"转写中… {int(frac * 100)}%")
            return result

        def close(self):
            try:
                super().close()
            except BrokenPipeError:
                pass

    old_tqdm = mlx_transcribe_mod.tqdm.tqdm

    def _tqdm_factory(*args, **kwargs):
        return _MLXTranscribeProgress(*args, **kwargs)

    mlx_transcribe_mod.tqdm.tqdm = _tqdm_factory
    try:
        return mlx_whisper.transcribe(
            audio_path,
            path_or_hf_repo=model_name,
            verbose=False,
        )
    finally:
        mlx_transcribe_mod.tqdm.tqdm = old_tqdm


def _transcribe_mlx(audio_path: str, model_name: str, progress_callback=None) -> dict:
    import os
    import importlib

    from core.hf_cache import HF_OFFICIAL_ENDPOINT, setup_hf_hub_cache

    setup_hf_hub_cache()
    os.environ["HF_ENDPOINT"] = HF_OFFICIAL_ENDPOINT

    mlx_whisper = importlib.import_module("mlx_whisper")
    mlx_transcribe_mod = importlib.import_module("mlx_whisper.transcribe")

    try:
        return _mlx_transcribe_once(
            mlx_whisper,
            audio_path,
            model_name,
            progress_callback=progress_callback,
            mlx_transcribe_mod=mlx_transcribe_mod,
        )
    except BrokenPipeError:
        # 管道后端或 tqdm 仍可能触发，降级为无进度条再试一次
        return mlx_whisper.transcribe(
            audio_path,
            path_or_hf_repo=model_name,
            verbose=False,
        )


def _transcribe_faster_whisper(
    audio_path: str, model_name: str, progress_callback=None
) -> dict:
    from faster_whisper import WhisperModel

    # 优先 GPU（Windows NVIDIA），否则 CPU
    device = "cpu"
    compute_type = "int8"
    try:
        import torch

        if torch.cuda.is_available():
            device = "cuda"
            compute_type = "float16"
    except ImportError:
        pass

    duration = _audio_duration_seconds(audio_path)
    model = WhisperModel(model_name, device=device, compute_type=compute_type)
    segments_iter, _info = model.transcribe(audio_path, language=None)

    segments = []
    text_parts = []
    for seg in segments_iter:
        segments.append({
            "start": float(seg.start),
            "end": float(seg.end),
            "text": seg.text,
        })
        text_parts.append(seg.text)
        if progress_callback and duration > 0:
            frac = min(1.0, float(seg.end) / duration)
            pct = 10 + int(frac * 80)
            progress_callback(pct, f"转写中… {int(frac * 100)}%")

    return {"text": "".join(text_parts), "segments": segments}


def transcribe(
    video_path: str,
    model_id: str,
    progress_callback=None,
) -> dict:
    """转写视频，返回 { text, segments }"""
    spec = get_model_spec(model_id)
    if not spec:
        raise ValueError(f"未知的 Whisper 模型: {model_id}")

    engine = spec["engine"]
    ad = audio_dir()
    ad.mkdir(parents=True, exist_ok=True)
    path_key = hashlib.md5(video_path.encode(), usedforsecurity=False).hexdigest()[:10]
    audio_path = str(ad / f"{Path(video_path).stem}_{path_key}.wav")

    try:
        extract_audio(video_path, audio_path)

        if progress_callback:
            progress_callback(10, "音频提取完成，正在转写...")

        if engine == "mlx":
            result = _transcribe_mlx(audio_path, model_id, progress_callback)
        elif engine == "faster_whisper":
            result = _transcribe_faster_whisper(audio_path, model_id, progress_callback)
        else:
            raise ValueError(f"不支持的转写引擎: {engine}")

        if progress_callback:
            progress_callback(90, "转写完成")

        return result

    finally:
        if os.path.exists(audio_path):
            os.remove(audio_path)
