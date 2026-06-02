"""同一视频的处理代次与 pipeline 互斥：防止并发 process_video 互相覆盖。"""

from __future__ import annotations

_run_ids: dict[str, int] = {}
_active_runs: dict[str, int] = {}


def is_pipeline_busy(video_id: str) -> bool:
    return video_id in _active_runs


def try_acquire_pipeline(video_id: str) -> int | None:
    """占用 pipeline；若该视频已有任务在跑则返回 None。"""
    if video_id in _active_runs:
        return None
    run_id = _run_ids.get(video_id, 0) + 1
    _run_ids[video_id] = run_id
    _active_runs[video_id] = run_id
    return run_id


def begin_video_run(video_id: str) -> int:
    """新建视频任务（新 video_id，无并发冲突）。"""
    run_id = _run_ids.get(video_id, 0) + 1
    _run_ids[video_id] = run_id
    _active_runs[video_id] = run_id
    return run_id


def release_pipeline(video_id: str, run_id: int) -> None:
    if _active_runs.get(video_id) == run_id:
        del _active_runs[video_id]


def is_stale_run(video_id: str, run_id: int) -> bool:
    return _run_ids.get(video_id, 0) != run_id
