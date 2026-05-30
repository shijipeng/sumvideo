"""视频文件路径：uploads 副本优先，source_path 仅兼容旧桌面记录。"""

from __future__ import annotations

from pathlib import Path

from core.storage_cleanup import find_upload_video_path
from db.database import get_video


def has_source_path(video_id: str) -> bool:
    video = get_video(video_id)
    if not video:
        return False
    sp = (video.get("source_path") or "").strip()
    return bool(sp)


def resolve_video_path(video_id: str) -> Path | None:
    """解析可播放/可转写的视频路径。"""
    upload = find_upload_video_path(video_id)
    if upload is not None:
        return upload
    video = get_video(video_id)
    if video is None:
        return None
    sp = (video.get("source_path") or "").strip()
    if sp:
        p = Path(sp)
        if p.is_file():
            return p
    return None
