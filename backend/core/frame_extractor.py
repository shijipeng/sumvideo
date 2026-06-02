"""章节配图：档 C 智能选帧（scene + 打分 + pHash 去重，节内多图）"""

from __future__ import annotations

import logging
import math
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from core.paths import upload_dir
from core.transcriber import _ffmpeg_bin

logger = logging.getLogger(__name__)

SCENE_THRESHOLD = 0.35
POST_SCENE_OFFSET_SEC = 0.25
MAX_CANDIDATES = 8
PHASH_HAMMING_THRESHOLD = 10
MAX_WIDTH = 1280
JPEG_QUALITY = "2"

# 按节时长自动决定配图数量：约每 FRAME_INTERVAL_SEC 秒 1 张
FRAME_INTERVAL_SEC = 45.0
MIN_FRAMES_PER_SECTION = 1
MAX_FRAMES_PER_SECTION = 8
SLOT_WINDOW_SEC = 8.0
MIN_START_OFFSET_SEC = 0.75
BLACK_MEAN = 25
WHITE_MEAN = 230

_PTS_TIME_RE = re.compile(r"pts_time:([0-9.]+)")


def _frames_dir(video_id: str) -> Path:
    return upload_dir() / video_id / "frames"


def _frame_count_for_duration(duration_sec: float) -> int:
    if duration_sec <= 0:
        return MIN_FRAMES_PER_SECTION
    count = max(MIN_FRAMES_PER_SECTION, math.ceil(duration_sec / FRAME_INTERVAL_SEC))
    return min(count, MAX_FRAMES_PER_SECTION)


def _section_start_offset(start: float) -> float:
    """避免在 0 秒或片头黑场截帧。"""
    if start < 2.0:
        return MIN_START_OFFSET_SEC
    return 0.3


def _frame_mean(image_path: Path) -> float | None:
    try:
        from PIL import Image
    except ImportError:
        return None
    try:
        with Image.open(image_path) as im:
            gray = im.convert("L")
            pixels = list(gray.getdata())
            if not pixels:
                return None
            return sum(pixels) / len(pixels)
    except OSError:
        return None


def _is_usable_frame(image_path: Path) -> bool:
    mean = _frame_mean(image_path)
    if mean is None:
        return True
    return BLACK_MEAN < mean < WHITE_MEAN


def _extract_frame(video_path: Path, time_sec: float, out_path: Path) -> bool:
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
            JPEG_QUALITY,
            "-vf",
            f"scale={MAX_WIDTH}:-1",
            "-y",
            str(out_path),
        ],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0 and out_path.is_file() and out_path.stat().st_size > 0


def _detect_scene_times(video_path: Path, start: float, end: float) -> list[float]:
    duration = max(0.1, end - start)
    cmd = [
        _ffmpeg_bin(),
        "-ss",
        str(max(0.0, start)),
        "-i",
        str(video_path),
        "-t",
        str(duration),
        "-vf",
        f"select='gt(scene\\,{SCENE_THRESHOLD})',showinfo",
        "-f",
        "null",
        "-",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    times: list[float] = []
    for line in (result.stderr or "").splitlines():
        m = _PTS_TIME_RE.search(line)
        if not m:
            continue
        t = start + float(m.group(1))
        if start <= t <= end:
            times.append(round(t + POST_SCENE_OFFSET_SEC, 2))
    return sorted(set(times))


def _uniform_samples(start: float, end: float, count: int = 3) -> list[float]:
    if end <= start:
        return [round(start, 2)]
    step = (end - start) / (count + 1)
    return [round(start + step * (i + 1), 2) for i in range(count)]


def _build_candidates(
    window_start: float,
    window_end: float,
    video_path: Path,
    *,
    prefer_time: float | None = None,
) -> list[float]:
    if window_end <= window_start:
        window_end = window_start + 0.5

    candidates: list[float] = []
    if prefer_time is not None:
        candidates.append(round(prefer_time, 2))

    scene_times = _detect_scene_times(video_path, window_start, window_end)
    candidates.extend(scene_times)
    if len(scene_times) < 2:
        candidates.extend(_uniform_samples(window_start, window_end))

    unique = sorted(set(candidates))
    return unique[:MAX_CANDIDATES]


def _slot_times(start: float, end: float, count: int) -> list[float]:
    offset = _section_start_offset(start)
    lo = start + offset
    hi = max(lo + 0.2, end - 0.15)
    if hi <= lo:
        return [round(lo, 2)]
    if count <= 1:
        return [round((lo + hi) / 2, 2)]
    step = (hi - lo) / (count - 1)
    return [round(lo + step * i, 2) for i in range(count)]


def _dhash(image_path: Path) -> int | None:
    try:
        from PIL import Image
    except ImportError:
        return None
    try:
        with Image.open(image_path) as im:
            gray = im.convert("L").resize((9, 8))
            pixels = list(gray.getdata())
        bits = 0
        for row in range(8):
            for col in range(8):
                left = pixels[row * 9 + col]
                right = pixels[row * 9 + col + 1]
                bits = (bits << 1) | (1 if left > right else 0)
        return bits
    except OSError:
        return None


def _hamming(a: int, b: int) -> int:
    return (a ^ b).bit_count()


def _score_frame(image_path: Path) -> float:
    if not _is_usable_frame(image_path):
        return -1.0

    try:
        from PIL import Image, ImageFilter
    except ImportError:
        return 1.0 if image_path.stat().st_size > 5000 else 0.0

    try:
        with Image.open(image_path) as im:
            gray = im.convert("L")
            pixels = list(gray.getdata())
            if not pixels:
                return -1.0
            mean = sum(pixels) / len(pixels)
            if mean < 50 or mean > 210:
                brightness = 0.5
            else:
                brightness = 1.0
            variance = sum((p - mean) ** 2 for p in pixels) / len(pixels)
            contrast = min(1.0, (variance**0.5) / 64.0)
            sharp = gray.filter(ImageFilter.FIND_EDGES)
            sharp_mean = sum(sharp.getdata()) / len(pixels)
            sharpness = min(1.0, sharp_mean / 32.0)
            return 0.3 * brightness + 0.4 * contrast + 0.3 * sharpness
    except OSError:
        return -1.0


def _pick_best_frame(
    video_path: Path,
    candidates: list[float],
    prev_hash: int | None,
    used_hashes: set[int],
    dest: Path,
    tmp_dir: Path,
    tag: str,
) -> tuple[int | None, float | None]:
    scored: list[tuple[float, float, Path]] = []
    for t in candidates:
        safe_t = str(t).replace(".", "_")
        out = tmp_dir / f"cand_{tag}_{safe_t}.jpg"
        if not _extract_frame(video_path, t, out):
            continue
        score = _score_frame(out)
        if score < 0:
            continue
        scored.append((score, t, out))

    if not scored:
        return None, None

    scored.sort(key=lambda x: (x[0], -abs(x[1])), reverse=True)

    for _score, t, path in scored:
        h = _dhash(path)
        if h is not None:
            if h in used_hashes:
                continue
            if (
                prev_hash is not None
                and _hamming(prev_hash, h) < PHASH_HAMMING_THRESHOLD
            ):
                continue
        shutil.copy(path, dest)
        picked_hash = _dhash(dest)
        return picked_hash, t

    return None, None


def _frame_url(video_id: str, section_index: int, frame_index: int) -> str:
    return f"/api/video/{video_id}/thumb/{section_index}/{frame_index}"


def attach_section_thumbnails(
    video_id: str,
    video_path: str | Path,
    sections: list[dict],
) -> list[dict]:
    """为每节按 duration 自动选多帧；写入 frames[] 与 thumbnail（首张）。"""
    path = Path(video_path)
    if not path.is_file() or not sections:
        return sections

    frames_dir = _frames_dir(video_id)
    if frames_dir.exists():
        shutil.rmtree(frames_dir, ignore_errors=True)
    frames_dir.mkdir(parents=True, exist_ok=True)

    prev_hash: int | None = None
    with tempfile.TemporaryDirectory(prefix="sumvideo_frame_") as tmp:
        tmp_dir = Path(tmp)
        for section_index, sec in enumerate(sections):
            sec.pop("frames", None)
            sec.pop("thumbnail", None)

            try:
                start = float(sec.get("start_time", 0))
                end = float(sec.get("end_time", start + FRAME_INTERVAL_SEC))
            except (TypeError, ValueError):
                continue

            duration = max(0.1, end - start)
            frame_count = _frame_count_for_duration(duration)
            slots = _slot_times(start, end, frame_count)
            section_frames: list[dict] = []
            used_hashes: set[int] = set()

            for frame_index, slot in enumerate(slots):
                half = SLOT_WINDOW_SEC / 2
                win_lo = max(start, slot - half)
                win_hi = min(end, slot + half)
                candidates = _build_candidates(
                    win_lo, win_hi, path, prefer_time=slot
                )
                dest = frames_dir / f"{section_index}_{frame_index}.jpg"
                picked_hash, picked_time = _pick_best_frame(
                    path,
                    candidates,
                    prev_hash,
                    used_hashes,
                    dest,
                    tmp_dir,
                    f"{section_index}_{frame_index}",
                )
                if picked_hash is None and not dest.is_file():
                    continue

                actual_time = picked_time if picked_time is not None else slot
                section_frames.append(
                    {
                        "time": round(actual_time, 1),
                        "url": _frame_url(video_id, section_index, frame_index),
                    }
                )
                if picked_hash is not None:
                    used_hashes.add(picked_hash)
                    prev_hash = picked_hash

            if section_frames:
                sec["frames"] = section_frames
                sec["thumbnail"] = section_frames[0]["url"]

    return sections


def get_thumbnail_path(
    video_id: str,
    section_index: int,
    frame_index: int | None = None,
) -> Path | None:
    if section_index < 0:
        return None
    frames_dir = _frames_dir(video_id)
    if frame_index is not None:
        if frame_index < 0:
            return None
        p = frames_dir / f"{section_index}_{frame_index}.jpg"
        return p if p.is_file() else None
    # 旧版单图：{section}.jpg
    legacy = frames_dir / f"{section_index}.jpg"
    if legacy.is_file():
        return legacy
    return get_thumbnail_path(video_id, section_index, 0)
