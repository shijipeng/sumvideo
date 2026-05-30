"""失败任务断点续跑：判断能否跳过 Whisper 仅重试笔记。"""

from __future__ import annotations

import json

_ERROR_MARKERS = (
    "处理已中断",
    "处理超时",
    "请重新上传",
    "DeepSeek API",
    "笔记生成超过",
    "转写进程",
    "转写输出",
    "无法连接 DeepSeek",
    "处理失败",
)


def _parse_segments(raw) -> list:
    if not raw:
        return []
    if isinstance(raw, list):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, list) else []
        except json.JSONDecodeError:
            return []
    return []


def video_has_resumable_transcript(video: dict) -> bool:
    """转写已落库且文本不像错误文案时，可从笔记阶段继续。"""
    segments = _parse_segments(video.get("transcript_segments"))
    if not segments:
        return False
    text = (video.get("transcript") or "").strip()
    if len(text) < 50:
        return False
    if (video.get("error_message") or "").strip():
        return True
    if video.get("status") != "error":
        return False
    head = text[:160]
    if any(m in head for m in _ERROR_MARKERS):
        return False
    return True


def video_error_message(video: dict) -> str | None:
    msg = (video.get("error_message") or "").strip()
    if msg:
        return msg
    if video.get("status") != "error":
        return None
    if video_has_resumable_transcript(video):
        return None
    t = (video.get("transcript") or "").strip()
    return t or None
