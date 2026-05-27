"""DeepSeek API：结构化视频笔记（概述 + 可定位分段）"""

import json
import re
from openai import OpenAI

from config import DEEPSEEK_BASE_URL
from core.settings_store import get_api_key, get_deepseek_model


def get_client() -> OpenAI:
    from core.settings_store import is_valid_api_key

    api_key = get_api_key()
    if not api_key:
        raise ValueError("请先在设置中配置 DeepSeek API Key")
    if not is_valid_api_key(api_key):
        raise ValueError(
            "DeepSeek API Key 无效（当前保存的不是 sk- 开头的密钥）。"
            "请打开「模型与 API 设置」重新填写。"
        )
    return OpenAI(api_key=api_key, base_url=DEEPSEEK_BASE_URL)


def _friendly_api_error(exc: Exception) -> str:
    msg = str(exc)
    lower = msg.lower()
    if "401" in msg or "authentication" in lower or "invalid api key" in lower:
        return (
            "DeepSeek API Key 无效或已过期，请在「模型与 API 设置」中重新填写正确的 sk- 密钥。"
        )
    return msg


NOTES_PROMPT = """你是视频学习笔记助手。根据语音转写文本，生成结构化笔记。

要求：
1. overview：用一段话（80–200 字）概括全片，不要分点。
2. sections：将视频划分为 4–8 个主题大块（不要细碎），按时间顺序覆盖全片。
   每个 section 包含：
   - title：4–8 字主题名
   - start_time、end_time：秒，一位小数，与转写时间大致对应
   - lead：1–2 句概括本节核心（不要用「总：」「分：」等前缀）
   - points：2–5 条要点展开细节（字符串数组，每条也不要加「总/分」前缀）
3. 不要复述口水话，合并重复信息，使用中文。

只返回 JSON 对象，格式如下（不要 markdown 代码块外的文字）：
{
  "overview": "……",
  "sections": [
    {
      "title": "术语入门",
      "start_time": 0.0,
      "end_time": 120.5,
      "lead": "本节核心概括……",
      "points": ["要点一", "要点二"]
    }
  ]
}"""


def _parse_json_content(content: str) -> dict:
    if "```json" in content:
        content = content.split("```json")[1].split("```")[0].strip()
    elif "```" in content:
        content = content.split("```")[1].split("```")[0].strip()
    return json.loads(content)


def _strip_note_label(text: str) -> str:
    s = text.strip()
    for pat in (r"^总[：:]\s*", r"^分[：:]\s*", r"^总述[：:]\s*", r"^分述[：:]\s*"):
        s = re.sub(pat, "", s)
    return s.strip()


def _normalize_sections(sections: list) -> list[dict]:
    out = []
    for i, raw in enumerate(sections):
        if not isinstance(raw, dict):
            continue
        title = str(raw.get("title") or f"第 {i + 1} 段").strip()
        try:
            start = round(float(raw.get("start_time", 0)), 1)
            end = round(float(raw.get("end_time", start)), 1)
        except (TypeError, ValueError):
            start, end = 0.0, 0.0
        if end < start:
            end = start
        lead = _strip_note_label(str(raw.get("lead") or ""))
        points_raw = raw.get("points") or []
        if isinstance(points_raw, str):
            points = [_strip_note_label(points_raw)] if points_raw.strip() else []
        else:
            points = [_strip_note_label(str(p)) for p in points_raw if str(p).strip()]
        out.append(
            {
                "title": title,
                "start_time": start,
                "end_time": end,
                "lead": lead,
                "points": points,
            }
        )
    return out


def generate_notes(transcript_text: str) -> dict:
    """生成 { overview, sections }，sections 同时用作章节导航与笔记分段。"""
    client = get_client()
    text = transcript_text[:60000]

    try:
        resp = client.chat.completions.create(
            model=get_deepseek_model(),
            messages=[
                {"role": "system", "content": NOTES_PROMPT},
                {"role": "user", "content": text},
            ],
            temperature=0.3,
            response_format={"type": "json_object"},
        )
    except Exception as e:
        raise ValueError(_friendly_api_error(e)) from e

    content = resp.choices[0].message.content or "{}"
    try:
        result = _parse_json_content(content)
    except (json.JSONDecodeError, IndexError):
        return {"overview": "", "sections": []}

    overview = str(result.get("overview") or "").strip()
    sections_raw = result.get("sections")
    if not isinstance(sections_raw, list):
        for key in ("chapters", "result", "data"):
            if isinstance(result.get(key), list):
                sections_raw = result[key]
                break
        else:
            sections_raw = []

    sections = _normalize_sections(sections_raw)
    return {"overview": overview, "sections": sections}


# 兼容旧调用（若仍有引用）
def analyze_chapters(transcript_text: str) -> list[dict]:
    notes = generate_notes(transcript_text)
    return notes["sections"]


def generate_summary(transcript_text: str) -> str:
    notes = generate_notes(transcript_text)
    return notes["overview"]
