"""转写合并 golden cases（与 web/src/lib/transcript.ts 对齐）"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.transcript_merge import MergeOptions, merge_transcript_segments


def test_merge_empty():
    assert merge_transcript_segments([]) == []


def test_merge_single():
    segs = [{"start_time": 0.0, "end_time": 1.0, "text": "你好"}]
    assert merge_transcript_segments(segs) == segs


def test_merge_adjacent_short_gap():
    segs = [
        {"start_time": 0.0, "end_time": 1.0, "text": "你好"},
        {"start_time": 1.5, "end_time": 2.5, "text": "世界"},
    ]
    merged = merge_transcript_segments(segs)
    assert len(merged) == 1
    assert merged[0]["text"] == "你好世界"
    assert merged[0]["start_time"] == 0.0
    assert merged[0]["end_time"] == 2.5


def test_merge_large_gap_splits():
    segs = [
        {"start_time": 0.0, "end_time": 1.0, "text": "A"},
        {"start_time": 10.0, "end_time": 11.0, "text": "B"},
    ]
    merged = merge_transcript_segments(segs)
    assert len(merged) == 2


def test_merge_respects_max_chars():
    segs = [
        {"start_time": 0.0, "end_time": 1.0, "text": "a" * 80},
        {"start_time": 1.2, "end_time": 2.0, "text": "b" * 80},
    ]
    merged = merge_transcript_segments(segs, MergeOptions(max_chars=100))
    assert len(merged) == 2
