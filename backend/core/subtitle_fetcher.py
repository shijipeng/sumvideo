"""在线视频字幕：yt-dlp 拉取并解析为 transcript_segments"""

from __future__ import annotations

import re
import tempfile
from dataclasses import dataclass
from pathlib import Path

import yt_dlp

from core.url_importer import _base_ydl_opts, validate_url_safe

MIN_SEGMENT_COUNT = 5
MIN_CHAR_COUNT = 100

_LANG_PRIORITY = (
    "zh-hans",
    "zh-cn",
    "zh",
    "zh-hant",
    "en",
    "en-us",
    "en-gb",
)


@dataclass
class SubtitleResult:
    transcript_text: str
    segments: list[dict]


def _parse_timestamp(ts: str) -> float:
    ts = ts.strip().replace(",", ".")
    parts = ts.split(":")
    if len(parts) == 3:
        h, m, s = parts
        return int(h) * 3600 + int(m) * 60 + float(s)
    if len(parts) == 2:
        m, s = parts
        return int(m) * 60 + float(s)
    return float(ts)


def _parse_vtt(content: str) -> list[dict]:
    segments: list[dict] = []
    blocks = re.split(r"\n\s*\n", content.replace("\r\n", "\n"))
    for block in blocks:
        lines = [ln.strip() for ln in block.split("\n") if ln.strip()]
        if len(lines) < 2:
            continue
        time_line = lines[1] if "-->" in lines[0] else lines[0]
        text_lines = lines[2:] if "-->" in lines[0] else lines[1:]
        if "-->" not in time_line:
            continue
        start_s, end_s = time_line.split("-->", 1)
        text = " ".join(text_lines).strip()
        text = re.sub(r"<[^>]+>", "", text)
        if not text:
            continue
        start = _parse_timestamp(start_s.strip())
        end = _parse_timestamp(end_s.strip())
        segments.append(
            {
                "start_time": round(start, 1),
                "end_time": round(max(end, start), 1),
                "text": text,
            }
        )
    return segments


def _parse_srt(content: str) -> list[dict]:
    content = re.sub(r"\d+\s*\n(\d{2}:\d{2}:\d{2}[,\.]\d{3}\s*-->)", r"\1", content)
    return _parse_vtt(content)


def _parse_subtitle_file(path: Path) -> list[dict]:
    text = path.read_text(encoding="utf-8", errors="replace")
    if path.suffix.lower() == ".srt":
        return _parse_srt(text)
    return _parse_vtt(text)


def _lang_rank(path: Path) -> int:
    name = path.stem.lower()
    for i, lang in enumerate(_LANG_PRIORITY):
        if lang in name:
            return i
    return len(_LANG_PRIORITY)


def _pick_subtitle_file(files: list[Path]) -> Path | None:
    if not files:
        return None
    return sorted(files, key=_lang_rank)[0]


def _is_valid(segments: list[dict]) -> bool:
    if len(segments) < MIN_SEGMENT_COUNT:
        return False
    total_chars = sum(len(s.get("text", "")) for s in segments)
    return total_chars >= MIN_CHAR_COUNT


def try_fetch_subtitles(url: str) -> SubtitleResult | None:
    validate_url_safe(url)
    with tempfile.TemporaryDirectory(prefix="sumvideo_subs_") as tmp:
        outtmpl = str(Path(tmp) / "sub")
        opts = {
            **_base_ydl_opts(),
            "skip_download": True,
            "writesubtitles": True,
            "writeautomaticsub": True,
            "subtitleslangs": ["all"],
            "subtitlesformat": "vtt/srt/best",
            "outtmpl": outtmpl,
        }
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([url])
        except Exception:
            return None

        files = list(Path(tmp).glob("*.vtt")) + list(Path(tmp).glob("*.srt"))
        picked = _pick_subtitle_file(files)
        if picked is None:
            return None
        segments = _parse_subtitle_file(picked)
        if not _is_valid(segments):
            return None
        transcript_text = "\n".join(s["text"] for s in segments).strip()
        return SubtitleResult(transcript_text=transcript_text, segments=segments)
