"""OCR 事件源（录屏/PPT）；可选依赖"""

from __future__ import annotations

import logging
import subprocess
import tempfile
from pathlib import Path

from core.frame_pipeline import FrameEvent, MIN_START_TIME, _score_frame
from core.scenarios import SOURCE_OCR
from core.transcriber import _ffmpeg_bin

logger = logging.getLogger(__name__)

MAX_WIDTH_OCR = 960
SAMPLE_EVERY_SEC = 2.0
TEXT_SIM_THRESHOLD = 0.92


def _ocr_extract_frame(video_path: Path, time_sec: float, out_path: Path) -> bool:
    import subprocess

    out_path.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [
            _ffmpeg_bin(),
            "-ss",
            str(max(0.0, time_sec)),
            "-i",
            str(video_path),
            "-frames:v",
            "1",
            "-q:v",
            "2",
            "-vf",
            f"scale={MAX_WIDTH_OCR}:-1",
            "-y",
            str(out_path),
        ],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0 and out_path.is_file() and out_path.stat().st_size > 0


def _ocr_text(image_path: Path) -> str:
    try:
        import pytesseract
        from PIL import Image
    except ImportError:
        return ""
    try:
        with Image.open(image_path) as im:
            text = pytesseract.image_to_string(im, lang="chi_sim+eng")
        return _normalize_text(text)
    except Exception as e:
        logger.debug("OCR 失败 %s: %s", image_path, e)
        return ""


def _normalize_text(text: str) -> str:
    import re

    s = re.sub(r"\s+", "", text or "")
    return s.lower()


def _text_similarity(a: str, b: str) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    # 简单字符集 Jaccard
    sa, sb = set(a), set(b)
    inter = len(sa & sb)
    union = len(sa | sb)
    return inter / union if union else 1.0


def _video_duration(video_path: Path) -> float:
    result = subprocess.run(
        [
            _ffmpeg_bin(),
            "-i",
            str(video_path),
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        text=True,
    )
    import re

    m = re.search(r"Duration: (\d+):(\d+):(\d+\.\d+)", result.stderr or "")
    if not m:
        return 3600.0
    h, mi, s = int(m.group(1)), int(m.group(2)), float(m.group(3))
    return h * 3600 + mi * 60 + s


def collect_ocr_events(
    video_path: Path,
    duration_hint: float | None = None,
) -> tuple[list[FrameEvent], set[float]]:
    """返回 (ocr 变化事件, scene 可丢弃的时间点集合)。"""
    events: list[FrameEvent] = []
    unchanged_scene_times: set[float] = set()
    try:
        import pytesseract  # noqa: F401
    except ImportError:
        logger.info("pytesseract 未安装，跳过 OCR 事件")
        return events, unchanged_scene_times

    path = Path(video_path)
    if not path.is_file():
        return events, unchanged_scene_times

    duration = duration_hint or _video_duration(path)
    prev_text = ""
    t = MIN_START_TIME

    with tempfile.TemporaryDirectory(prefix="sumvideo_ocr_") as tmp:
        tmp_dir = Path(tmp)
        while t < duration - 0.5:
            out = tmp_dir / f"ocr_{t:.1f}.jpg"
            if not _ocr_extract_frame(path, t, out):
                t += SAMPLE_EVERY_SEC
                continue
            if _score_frame(out) < 0:
                t += SAMPLE_EVERY_SEC
                continue
            text = _ocr_text(out)
            sim = _text_similarity(prev_text, text)
            if prev_text and sim < TEXT_SIM_THRESHOLD and text:
                events.append(FrameEvent(t, SOURCE_OCR))
            elif prev_text and sim >= TEXT_SIM_THRESHOLD:
                unchanged_scene_times.add(round(t, 1))
            if text:
                prev_text = text
            t += SAMPLE_EVERY_SEC

    return events, unchanged_scene_times


def ocr_available() -> bool:
    try:
        import pytesseract  # noqa: F401

        return True
    except ImportError:
        return False
