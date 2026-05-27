"""uploads 目录清理：避免视频文件无限增长"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta
from pathlib import Path

import config
from db.database import (
    delete_video,
    hashes_with_duplicates,
    list_all_video_ids,
    list_ids_by_hash,
    list_video_ids_by_status,
    mark_tasks_stale_as_error,
)

logger = logging.getLogger(__name__)

UPLOAD_DIR = Path(config.UPLOAD_DIR)

VIDEO_EXTENSIONS = (
    ".mp4", ".avi", ".mov", ".mkv", ".webm", ".flv", ".wmv",
    ".m4v", ".mpeg", ".mpg", ".3gp", ".ts",
)

# 卡在 pending/processing 超过此时长视为僵尸任务
STALE_TASK_HOURS = int(getattr(config, "STALE_TASK_HOURS", 48))


def find_video_path(video_id: str) -> Path | None:
    for ext in VIDEO_EXTENSIONS:
        path = UPLOAD_DIR / f"{video_id}{ext}"
        if path.is_file():
            return path
    return None


def delete_video_file(video_id: str) -> bool:
    """仅删除磁盘上的视频文件，保留数据库记录。"""
    path = find_video_path(video_id)
    if path is None:
        return False
    try:
        os.remove(path)
        logger.info("已删除视频文件: %s", path.name)
        return True
    except OSError as e:
        logger.warning("删除视频文件失败 %s: %s", path, e)
        return False


def purge_video_record(video_id: str) -> None:
    """删除视频文件 + 数据库记录（用户删历史、去重弃用记录）。"""
    delete_video_file(video_id)
    delete_video(video_id)


def purge_duplicate_records() -> int:
    """同 file_hash 只保留最新一条，其余记录与文件一并删除。"""
    removed = 0
    for file_hash in hashes_with_duplicates():
        ids = list_ids_by_hash(file_hash)
        for old_id in ids[1:]:
            purge_video_record(old_id)
            removed += 1
    if removed:
        logger.info("去重清理: 删除 %s 条重复任务", removed)
    return removed


def purge_files_for_failed_tasks() -> int:
    """处理失败 (error) 的任务：保留 DB 供查看/删历史，删除占空间的视频文件。"""
    count = 0
    for vid in list_video_ids_by_status(("error",)):
        if delete_video_file(vid):
            count += 1
    if count:
        logger.info("失败任务: 删除 %s 个视频文件", count)
    return count


def purge_stale_in_progress_tasks() -> int:
    """长时间未完成的 pending/processing：标记为 error 并删除视频文件。"""
    stale_ids = mark_tasks_stale_as_error(STALE_TASK_HOURS)
    count = 0
    for vid in stale_ids:
        if delete_video_file(vid):
            count += 1
    if stale_ids:
        logger.info("僵尸任务: 标记 %s 条为 error，删除 %s 个视频文件", len(stale_ids), count)
    return count


def purge_orphan_and_temp_files() -> int:
    """删除无 DB 记录的视频文件，以及上传中断留下的 temp_* 文件。"""
    known_ids = set(list_all_video_ids())
    removed = 0
    if not UPLOAD_DIR.is_dir():
        return 0

    for path in UPLOAD_DIR.iterdir():
        if not path.is_file():
            continue
        name = path.name
        if name.startswith("temp_"):
            try:
                os.remove(path)
                removed += 1
            except OSError:
                pass
            continue

        suffix = path.suffix.lower()
        if suffix not in VIDEO_EXTENSIONS:
            continue

        video_id = path.stem
        if video_id not in known_ids:
            try:
                os.remove(path)
                removed += 1
                logger.info("已删除孤儿视频: %s", name)
            except OSError:
                pass

    if removed:
        logger.info("孤儿/临时文件: 删除 %s 个", removed)
    return removed


def run_storage_cleanup() -> dict[str, int]:
    """启动或维护时执行全套清理，返回各步骤删除数量。"""
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    stats = {
        "duplicates": purge_duplicate_records(),
        "failed_files": purge_files_for_failed_tasks(),
        "stale_tasks": purge_stale_in_progress_tasks(),
        "orphans": purge_orphan_and_temp_files(),
    }
    return stats


def on_processing_failed(video_id: str) -> None:
    """单任务处理失败：立即删除视频文件，避免失败后仍占磁盘。"""
    delete_video_file(video_id)
