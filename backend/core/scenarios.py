"""可扩展视频场景注册表：meta 路由与选图 FrameProfile"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any

META_SCHEMA_VERSION = 1

VALID_VIDEO_TYPES = frozenset(
    {
        "lecture_screen",
        "talking_head",
        "interview",
        "vlog_dynamic",
        "demo_hands_on",
        "general",
    }
)

VALID_SUMMARY_STYLES = frozenset(
    {
        "tutorial",
        "opinion",
        "news",
        "review",
        "meeting",
        "general",
    }
)

SOURCE_SCENE = "scene"
SOURCE_TRANSCRIPT = "transcript"
SOURCE_OCR = "ocr"
SOURCE_MERGED = "merged"

FILTER_BLACK = "black_frame"
FILTER_PHASH = "phash_dedup"
FILTER_OCR_UNCHANGED = "ocr_unchanged"
FILTER_MIN_GAP = "min_gap"
FILTER_SECTION_CAP = "section_cap"


@dataclass(frozen=True)
class FrameProfile:
    event_sources: tuple[str, ...] = (SOURCE_SCENE, SOURCE_TRANSCRIPT)
    filters: tuple[str, ...] = (FILTER_BLACK, FILTER_PHASH, FILTER_MIN_GAP)
    merge_delta_sec: float = 3.0
    min_gap_sec: float = 5.0
    max_frames_per_section: int | None = None
    transcript_gap_sec: float = 1.5
    scene_threshold: float = 27.0
    scene_min_len_frames: int = 15


@dataclass(frozen=True)
class ScenarioDefinition:
    id: str
    label: str
    frame_profile: FrameProfile
    summary_hints: str = ""


def _profile_general() -> FrameProfile:
    return FrameProfile()


def _profile_talking() -> FrameProfile:
    return FrameProfile(
        event_sources=(SOURCE_TRANSCRIPT, SOURCE_SCENE),
        merge_delta_sec=4.0,
        min_gap_sec=6.0,
    )


def _profile_screen() -> FrameProfile:
    return FrameProfile(
        event_sources=(SOURCE_OCR, SOURCE_SCENE, SOURCE_TRANSCRIPT),
        filters=(FILTER_BLACK, FILTER_PHASH, FILTER_OCR_UNCHANGED, FILTER_MIN_GAP),
        merge_delta_sec=2.0,
        min_gap_sec=4.0,
    )


def _profile_dynamic() -> FrameProfile:
    return FrameProfile(
        event_sources=(SOURCE_SCENE, SOURCE_TRANSCRIPT),
        merge_delta_sec=2.0,
        min_gap_sec=3.0,
        max_frames_per_section=12,
        filters=(FILTER_BLACK, FILTER_PHASH, FILTER_MIN_GAP, FILTER_SECTION_CAP),
    )


SCENARIOS: dict[str, ScenarioDefinition] = {
    "general": ScenarioDefinition(
        id="general",
        label="通用",
        frame_profile=_profile_general(),
        summary_hints="平衡概述与要点，适合无法明确分类的内容。",
    ),
    "lecture_screen": ScenarioDefinition(
        id="lecture_screen",
        label="录屏/PPT 教程",
        frame_profile=_profile_screen(),
        summary_hints="突出步骤、概念定义与操作顺序；要点宜可对照屏幕内容。",
    ),
    "talking_head": ScenarioDefinition(
        id="talking_head",
        label="口播讲解",
        frame_profile=_profile_talking(),
        summary_hints="以观点与论证为主，按话题分段，避免堆砌转写口水话。",
    ),
    "interview": ScenarioDefinition(
        id="interview",
        label="访谈对话",
        frame_profile=_profile_talking(),
        summary_hints="区分嘉宾与话题线索，保留关键问答与结论。",
    ),
    "vlog_dynamic": ScenarioDefinition(
        id="vlog_dynamic",
        label="实拍/Vlog",
        frame_profile=_profile_dynamic(),
        summary_hints="按场景与叙事线分段，概括画面信息与旁白要点。",
    ),
    "demo_hands_on": ScenarioDefinition(
        id="demo_hands_on",
        label="实操演示",
        frame_profile=FrameProfile(
            event_sources=(SOURCE_SCENE, SOURCE_TRANSCRIPT),
            merge_delta_sec=3.0,
            min_gap_sec=5.0,
        ),
        summary_hints="强调操作步骤、输入输出与易错点。",
    ),
}


def list_scenarios_for_prompt() -> str:
    lines = []
    for s in SCENARIOS.values():
        lines.append(f"- video_type `{s.id}`：{s.label}。{s.summary_hints}")
    return "\n".join(lines)


def list_summary_styles_for_prompt() -> str:
    return (
        "- summary_style `tutorial`：教程/知识讲解\n"
        "- summary_style `opinion`：观点评论\n"
        "- summary_style `news`：资讯报道\n"
        "- summary_style `review`：评测复盘\n"
        "- summary_style `meeting`：会议记录\n"
        "- summary_style `general`：通用"
    )


def normalize_meta(raw: dict | None) -> dict:
    if not raw or not isinstance(raw, dict):
        return {
            "schema_version": META_SCHEMA_VERSION,
            "video_type": "general",
            "summary_style": "general",
            "industry": "",
            "confidence": 0.0,
            "type_reason": "",
        }
    video_type = str(raw.get("video_type") or "general").strip()
    video_type_raw = None
    if video_type not in VALID_VIDEO_TYPES:
        video_type_raw = video_type
        video_type = "general"
    summary_style = str(raw.get("summary_style") or "general").strip()
    if summary_style not in VALID_SUMMARY_STYLES:
        summary_style = "general"
    try:
        confidence = float(raw.get("confidence", 0))
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))
    out: dict[str, Any] = {
        "schema_version": META_SCHEMA_VERSION,
        "video_type": video_type,
        "summary_style": summary_style,
        "industry": str(raw.get("industry") or "").strip()[:120],
        "confidence": round(confidence, 2),
        "type_reason": str(raw.get("type_reason") or "").strip()[:300],
    }
    if video_type_raw:
        out["video_type_raw"] = video_type_raw
    return out


def get_scenario(scenario_id: str) -> ScenarioDefinition:
    return SCENARIOS.get(scenario_id) or SCENARIOS["general"]


def resolve_scenario(meta: dict | None, local_fallback_id: str | None = None) -> ScenarioDefinition:
    normalized = normalize_meta(meta)
    vid = normalized["video_type"]
    if normalized["confidence"] < 0.5 and local_fallback_id and local_fallback_id in SCENARIOS:
        return get_scenario(local_fallback_id)
    return get_scenario(vid)


def scenario_label(scenario_id: str) -> str:
    return get_scenario(scenario_id).label


def apply_frame_density(profile: FrameProfile, density: str | None = None) -> FrameProfile:
    """可选配图密度：compact / standard / detailed。"""
    d = (density or "standard").strip().lower()
    if d == "compact":
        return replace(
            profile,
            min_gap_sec=profile.min_gap_sec * 1.5,
            merge_delta_sec=profile.merge_delta_sec * 1.25,
        )
    if d == "detailed":
        return replace(
            profile,
            min_gap_sec=max(2.0, profile.min_gap_sec * 0.65),
            merge_delta_sec=max(1.0, profile.merge_delta_sec * 0.75),
        )
    return profile
