"""异步配图阶段：partial success，不拖垮文字笔记"""

from __future__ import annotations

import asyncio
import logging
import os

import config
from core.frame_ocr import collect_ocr_events, ocr_available
from core.frame_pipeline import (
    attach_section_frames,
    classify_video_style_local,
    collect_scene_events,
    collect_transcript_events,
)
from core.scenarios import SOURCE_OCR, apply_frame_density, resolve_scenario
from core.video_paths import resolve_video_path
from db.database import get_video, update_chapters_frames, update_frame_status

logger = logging.getLogger(__name__)

_frame_tasks: set[str] = set()


def is_frame_stage_running(video_id: str) -> bool:
    return video_id in _frame_tasks


async def run_frame_stage(video_id: str) -> None:
    if video_id in _frame_tasks:
        logger.info("配图任务 %s 已在运行", video_id)
        return
    _frame_tasks.add(video_id)
    try:
        await _run_frame_stage_inner(video_id)
    finally:
        _frame_tasks.discard(video_id)


async def _run_frame_stage_inner(video_id: str) -> None:
    row = get_video(video_id)
    if not row:
        return

    video_path = resolve_video_path(video_id)
    if not video_path or not os.path.isfile(video_path):
        update_frame_status(video_id, "skipped", 0, 0, error_msg=None)
        return

    chapters = row.get("chapters") or []
    if not chapters:
        update_frame_status(video_id, "skipped", 0, 0, error_msg="无章节结构，跳过配图")
        return

    segments = row.get("transcript_segments") or []
    notes_meta = row.get("notes_meta")
    if isinstance(notes_meta, str):
        import json

        try:
            notes_meta = json.loads(notes_meta)
        except json.JSONDecodeError:
            notes_meta = None

    update_frame_status(video_id, "processing", 0, 0, error_msg=None)

    def on_progress(done: int, total: int) -> None:
        update_frame_status(video_id, "processing", done, max(total, 1), error_msg=None)

    loop = asyncio.get_running_loop()

    def do_frames() -> list[dict]:
        from pathlib import Path

        scene_ev = collect_scene_events(Path(video_path), resolve_scenario(notes_meta).frame_profile)
        trans_ev = collect_transcript_events(segments, resolve_scenario(notes_meta).frame_profile)
        local_style = classify_video_style_local(len(scene_ev), len(trans_ev))
        scenario = resolve_scenario(notes_meta, local_fallback_id=local_style)
        profile = apply_frame_density(
            scenario.frame_profile,
            getattr(config, "SUMVIDEO_FRAME_DENSITY", "standard"),
        )

        ocr_events = None
        ocr_unchanged = None
        use_ocr = SOURCE_OCR in profile.event_sources
        if use_ocr and getattr(config, "SUMVIDEO_OCR", True) and ocr_available():
            ocr_events, ocr_unchanged = collect_ocr_events(Path(video_path))
        elif use_ocr and not ocr_available():
            logger.warning("OCR 未就绪，lecture_screen 降级为 scene+transcript")

        sections = [dict(s) for s in chapters]
        for sec in sections:
            sec.pop("frames", None)
            sec.pop("thumbnail", None)

        return attach_section_frames(
            video_id,
            video_path,
            sections,
            segments,
            profile,
            ocr_events=ocr_events,
            ocr_unchanged_times=ocr_unchanged,
            on_progress=on_progress,
        )

    try:
        updated = await loop.run_in_executor(None, do_frames)
        update_chapters_frames(video_id, updated)
        total_frames = sum(len(s.get("frames") or []) for s in updated)
        update_frame_status(
            video_id,
            "done",
            total_frames,
            max(total_frames, 1),
            error_msg=None,
        )
        logger.info("配图完成 %s，共 %s 张", video_id, total_frames)
    except Exception as e:
        logger.exception("配图失败 %s", video_id)
        update_frame_status(video_id, "error", 0, 0, error_msg=str(e))


def schedule_frame_stage(video_id: str) -> None:
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(run_frame_stage(video_id))
    except RuntimeError:
        asyncio.run(run_frame_stage(video_id))
