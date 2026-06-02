"""转写句段合并（与 web/src/lib/transcript.ts 对齐）"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class MergeOptions:
    max_chars: int = 120
    max_duration_sec: float = 45.0
    max_gap_sec: float = 2.0


def merge_transcript_segments(
    segments: list[dict[str, Any]] | None,
    opts: MergeOptions | None = None,
) -> list[dict[str, Any]]:
    if not segments:
        return []
    o = opts or MergeOptions()
    sorted_segs = sorted(segments, key=lambda s: float(s.get("start_time", 0)))
    result: list[dict[str, Any]] = []
    current = dict(sorted_segs[0])

    for nxt in sorted_segs[1:]:
        gap = float(nxt["start_time"]) - float(current["end_time"])
        merged_text = str(current.get("text", "")) + str(nxt.get("text", ""))
        merged_duration = float(nxt["end_time"]) - float(current["start_time"])
        if (
            gap <= o.max_gap_sec
            and len(merged_text) <= o.max_chars
            and merged_duration <= o.max_duration_sec
        ):
            current = {
                "start_time": current["start_time"],
                "end_time": max(float(current["end_time"]), float(nxt["end_time"])),
                "text": merged_text,
            }
        else:
            result.append(current)
            current = dict(nxt)
    result.append(current)
    return result
