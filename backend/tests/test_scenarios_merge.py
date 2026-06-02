"""PR0 单测：场景 registry 与转写合并"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.frame_pipeline import FrameEvent, merge_events
from core.scenarios import normalize_meta, resolve_scenario, get_scenario
from core.transcript_merge import merge_transcript_segments


def test_merge_transcript_segments_golden():
    segments = [
        {"start_time": 0.0, "end_time": 1.0, "text": "你好"},
        {"start_time": 1.5, "end_time": 2.5, "text": "世界"},
        {"start_time": 10.0, "end_time": 11.0, "text": "下一段"},
    ]
    merged = merge_transcript_segments(segments)
    assert len(merged) == 2
    assert merged[0]["text"] == "你好世界"
    assert merged[1]["start_time"] == 10.0


def test_normalize_meta_unknown_type():
    meta = normalize_meta({"video_type": "unknown_xyz", "confidence": 0.9})
    assert meta["video_type"] == "general"
    assert meta.get("video_type_raw") == "unknown_xyz"


def test_resolve_scenario_low_confidence_fallback():
    meta = normalize_meta({"video_type": "lecture_screen", "confidence": 0.2})
    s = resolve_scenario(meta, local_fallback_id="talking_head")
    assert s.id == "talking_head"


def test_merge_events():
    events = [
        FrameEvent(10.0, "scene"),
        FrameEvent(11.5, "transcript"),
        FrameEvent(30.0, "scene"),
    ]
    merged = merge_events(events, 3.0)
    assert len(merged) == 2


def test_registry_has_general():
    assert get_scenario("general").label == "通用"
