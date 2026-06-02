"""事件驱动章节配图 pipeline"""

from __future__ import annotations

import logging
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from core.frame_extractor import get_thumbnail_path  # noqa: F401 re-export
from core.paths import upload_dir
from core.scenarios import (
    FILTER_BLACK,
    FILTER_MIN_GAP,
    FILTER_OCR_UNCHANGED,
    FILTER_PHASH,
    FILTER_SECTION_CAP,
    SOURCE_OCR,
    SOURCE_SCENE,
    SOURCE_TRANSCRIPT,
    FrameProfile,
)
from core.transcriber import _ffmpeg_bin
from core.transcript_merge import merge_transcript_segments

logger = logging.getLogger(__name__)

MAX_WIDTH = 1280
JPEG_QUALITY = "2"
BLACK_MEAN = 25
WHITE_MEAN = 230
PHASH_HAMMING_THRESHOLD = 10
MIN_START_TIME = 0.75

ProgressCallback = Callable[[int, int], None]


@dataclass
class FrameEvent:
    time: float
    source: str
    weight: int = 0

    def __post_init__(self) -> None:
        self.time = round(float(self.time), 2)
        if self.source == SOURCE_TRANSCRIPT:
            self.weight = 2
        elif self.source == SOURCE_OCR:
            self.weight = 3
        elif self.source == SOURCE_SCENE:
            self.weight = 1


def _frames_dir(video_id: str) -> Path:
    return upload_dir() / video_id / "frames"


def _frame_url(video_id: str, section_index: int, frame_index: int) -> str:
    return f"/api/video/{video_id}/thumb/{section_index}/{frame_index}"


def merge_events(events: list[FrameEvent], merge_delta_sec: float) -> list[FrameEvent]:
    if not events:
        return []
    sorted_ev = sorted(events, key=lambda e: e.time)
    merged: list[FrameEvent] = [sorted_ev[0]]
    for ev in sorted_ev[1:]:
        last = merged[-1]
        if ev.time - last.time < merge_delta_sec:
            if ev.weight >= last.weight:
                merged[-1] = FrameEvent(
                    time=(last.time + ev.time) / 2,
                    source=ev.source if ev.weight >= last.weight else last.source,
                )
            else:
                merged[-1] = FrameEvent(
                    time=(last.time + ev.time) / 2,
                    source=last.source,
                )
        else:
            merged.append(ev)
    return merged


def collect_scene_events(video_path: Path, profile: FrameProfile) -> list[FrameEvent]:
    try:
        from scenedetect import ContentDetector, SceneManager, open_video
    except ImportError:
        logger.warning("PySceneDetect 未安装，跳过 scene 事件")
        return []

    events: list[FrameEvent] = []
    try:
        video = open_video(str(video_path))
        manager = SceneManager()
        manager.add_detector(
            ContentDetector(
                threshold=profile.scene_threshold,
                min_scene_len=profile.scene_min_len_frames,
            )
        )
        manager.detect_scenes(video)
        scene_list = manager.get_scene_list()
        for start, end in scene_list:
            start_sec = start.get_seconds()
            end_sec = end.get_seconds()
            if end_sec - start_sec > 0.6:
                t = start_sec + 0.3
            else:
                t = (start_sec + end_sec) / 2
            if t >= MIN_START_TIME:
                events.append(FrameEvent(t, SOURCE_SCENE))
    except Exception as e:
        logger.warning("scene 检测失败: %s", e)
    return events


def collect_transcript_events(
    segments: list[dict],
    profile: FrameProfile,
) -> list[FrameEvent]:
    events: list[FrameEvent] = []
    merged = merge_transcript_segments(segments)
    for i, seg in enumerate(merged):
        try:
            t = float(seg.get("start_time", 0))
        except (TypeError, ValueError):
            continue
        if t >= MIN_START_TIME:
            events.append(FrameEvent(t, SOURCE_TRANSCRIPT))
        if i > 0:
            try:
                prev_end = float(merged[i - 1].get("end_time", 0))
                gap = t - prev_end
                if gap > profile.transcript_gap_sec:
                    mid = prev_end + gap / 2
                    if mid >= MIN_START_TIME:
                        events.append(FrameEvent(mid, SOURCE_TRANSCRIPT))
            except (TypeError, ValueError):
                pass
    return events


def classify_video_style_local(scene_count: int, transcript_count: int) -> str:
    if scene_count <= 2 and transcript_count >= 3:
        return "talking_head"
    if scene_count >= 8:
        return "vlog_dynamic"
    return "general"


def _extract_frame(video_path: Path, time_sec: float, out_path: Path) -> bool:
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
            if mean <= BLACK_MEAN or mean >= WHITE_MEAN:
                return -1.0
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


def _pick_representative(
    video_path: Path,
    event: FrameEvent,
    tmp_dir: Path,
    tag: str,
    prev_hash: int | None,
    used_hashes: set[int],
) -> tuple[Path | None, float | None, int | None]:
    candidates = [event.time, event.time - 0.5, event.time + 0.5]
    scored: list[tuple[float, float, Path]] = []
    for t in candidates:
        safe = str(t).replace(".", "_")
        out = tmp_dir / f"pick_{tag}_{safe}.jpg"
        if not _extract_frame(video_path, t, out):
            continue
        score = _score_frame(out)
        if score < 0:
            continue
        scored.append((score, t, out))
    if not scored:
        return None, None, None
    scored.sort(key=lambda x: x[0], reverse=True)
    for _s, t, path in scored:
        h = _dhash(path)
        if h is not None:
            if h in used_hashes:
                continue
            if prev_hash is not None and _hamming(prev_hash, h) < PHASH_HAMMING_THRESHOLD:
                continue
        return path, t, h
    return scored[0][2], scored[0][1], _dhash(scored[0][2])


def _assign_section_index(time_sec: float, sections: list[dict]) -> int | None:
    """严格按章节时间窗分配；窗口外的事件丢弃，避免错节与「其他」。"""
    if not sections:
        return None
    last = len(sections) - 1
    for i, sec in enumerate(sections):
        try:
            start = float(sec.get("start_time", 0))
            end = float(sec.get("end_time", start))
        except (TypeError, ValueError):
            continue
        if i == last:
            if start - 0.3 <= time_sec <= end + 1.0:
                return i
        elif start - 0.3 <= time_sec < end + 0.3:
            return i
    return None


def _apply_min_gap(events: list[FrameEvent], min_gap: float) -> list[FrameEvent]:
    if min_gap <= 0:
        return events
    out: list[FrameEvent] = []
    for ev in sorted(events, key=lambda e: e.time):
        if out and ev.time - out[-1].time < min_gap:
            continue
        out.append(ev)
    return out


def _apply_section_cap(
    section_frames: dict[int, list[dict]],
    cap: int | None,
) -> dict[int, list[dict]]:
    if not cap:
        return section_frames
    for idx in list(section_frames.keys()):
        frames = section_frames[idx]
        if len(frames) > cap:
            step = len(frames) / cap
            picked = [frames[int(i * step)] for i in range(cap)]
            section_frames[idx] = picked
    return section_frames


def attach_section_frames(
    video_id: str,
    video_path: str | Path,
    sections: list[dict],
    transcript_segments: list[dict] | None,
    profile: FrameProfile,
    *,
    ocr_events: list[FrameEvent] | None = None,
    ocr_unchanged_times: set[float] | None = None,
    on_progress: ProgressCallback | None = None,
) -> list[dict]:
    path = Path(video_path)
    if not path.is_file() or not sections:
        return sections

    for sec in sections:
        sec.pop("frames", None)
        sec.pop("thumbnail", None)

    events: list[FrameEvent] = []
    if SOURCE_SCENE in profile.event_sources:
        events.extend(collect_scene_events(path, profile))
    if SOURCE_TRANSCRIPT in profile.event_sources and transcript_segments:
        events.extend(collect_transcript_events(transcript_segments, profile))
    if SOURCE_OCR in profile.event_sources and ocr_events:
        events.extend(ocr_events)

    events = merge_events(events, profile.merge_delta_sec)
    events = [e for e in events if e.time >= MIN_START_TIME]

    if FILTER_OCR_UNCHANGED in profile.filters and ocr_unchanged_times:
        events = [e for e in events if e.source != SOURCE_SCENE or round(e.time, 1) not in ocr_unchanged_times]

    if FILTER_MIN_GAP in profile.filters:
        events = _apply_min_gap(events, profile.min_gap_sec)

    total = len(events)
    if on_progress:
        on_progress(0, total)

    frames_dir = _frames_dir(video_id)
    if frames_dir.exists():
        shutil.rmtree(frames_dir, ignore_errors=True)
    frames_dir.mkdir(parents=True, exist_ok=True)

    section_frames: dict[int, list[dict]] = {i: [] for i in range(len(sections))}
    section_counters: dict[int, int] = {i: 0 for i in range(len(sections))}
    prev_hash: int | None = None
    used_hashes: set[int] = set()
    done = 0

    with tempfile.TemporaryDirectory(prefix="sumvideo_frame_") as tmp:
        tmp_dir = Path(tmp)
        for ev in events:
            sec_idx = _assign_section_index(ev.time, sections)
            if sec_idx is None:
                done += 1
                if on_progress:
                    on_progress(done, total)
                continue
            if FILTER_SECTION_CAP in profile.filters and profile.max_frames_per_section:
                if len(section_frames.get(sec_idx, [])) >= profile.max_frames_per_section:
                    done += 1
                    if on_progress:
                        on_progress(done, total)
                    continue

            fidx = section_counters[sec_idx]
            dest = frames_dir / f"{sec_idx}_{fidx}.jpg"
            picked, picked_time, picked_hash = _pick_representative(
                path, ev, tmp_dir, f"{sec_idx}_{fidx}", prev_hash, used_hashes
            )
            if picked is None:
                done += 1
                if on_progress:
                    on_progress(done, total)
                continue
            shutil.copy(picked, dest)
            actual = picked_time if picked_time is not None else ev.time
            section_frames[sec_idx].append(
                {
                    "time": round(actual, 1),
                    "url": _frame_url(video_id, sec_idx, fidx),
                }
            )
            section_counters[sec_idx] = fidx + 1
            if picked_hash is not None:
                used_hashes.add(picked_hash)
                prev_hash = picked_hash
            done += 1
            if on_progress:
                on_progress(done, total)

    if FILTER_SECTION_CAP in profile.filters:
        section_frames = _apply_section_cap(section_frames, profile.max_frames_per_section)

    for i, sec in enumerate(sections):
        frames = section_frames.get(i) or []
        if frames:
            sec["frames"] = frames
            sec["thumbnail"] = frames[0]["url"]

    return sections
