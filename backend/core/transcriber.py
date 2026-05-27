"""视频转写：Mac 用 MLX Whisper，Windows/Linux 用 faster-whisper"""

import os
import subprocess
from pathlib import Path

from core.hf_cache import setup_hf_hub_cache
from core.whisper_models import get_model_spec

setup_hf_hub_cache()


def extract_audio(video_path: str, audio_path: str) -> str:
    """用 ffmpeg 从视频中提取音频"""
    result = subprocess.run(
        [
            "ffmpeg", "-i", video_path,
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
                "ffprobe",
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


def _transcribe_mlx(audio_path: str, model_name: str, progress_callback=None) -> dict:
    import os

    from tqdm.auto import tqdm as BaseTqdm

    from core.hf_cache import HF_OFFICIAL_ENDPOINT, setup_hf_hub_cache

    setup_hf_hub_cache()
    os.environ["HF_ENDPOINT"] = HF_OFFICIAL_ENDPOINT

    # 必须先加载子模块：mlx_whisper.__init__ 会把 transcribe 导出为函数，
    # 若先 import mlx_whisper，则 mlx_whisper.transcribe 指向函数而非子模块。
    import importlib

    mlx_whisper = importlib.import_module("mlx_whisper")
    mlx_transcribe_mod = importlib.import_module("mlx_whisper.transcribe")

    if not progress_callback:
        return mlx_whisper.transcribe(
            audio_path,
            path_or_hf_repo=model_name,
            verbose=False,
        )

    class _MLXTranscribeProgress(BaseTqdm):
        """把 mlx_whisper 内部 tqdm（按帧）同步到任务进度"""

        def __init__(self, *args, **kwargs):
            kwargs.setdefault("disable", False)
            self._cb = progress_callback
            super().__init__(*args, **kwargs)

        def update(self, n=1):
            result = super().update(n)
            if self._cb and self.total and self.total > 0:
                frac = min(1.0, self.n / self.total)
                pct = 10 + int(frac * 80)
                self._cb(pct, f"转写中… {int(frac * 100)}%")
            return result

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
    audio_dir = Path(video_path).parent / ".audio_temp"
    audio_dir.mkdir(parents=True, exist_ok=True)
    audio_path = str(audio_dir / f"{Path(video_path).stem}.wav")

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
        try:
            audio_dir.rmdir()
        except OSError:
            pass
