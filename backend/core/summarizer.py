"""DeepSeek API：背景推断 + 结构化笔记（单次调用）"""

import json
import logging
import re
from typing import Any

import httpx
from openai import APIConnectionError, APIStatusError, APITimeoutError, OpenAI

from config import DEEPSEEK_BASE_URL
from core.scenarios import (
    list_scenarios_for_prompt,
    list_summary_styles_for_prompt,
    normalize_meta,
)
from core.settings_store import get_api_key, get_deepseek_model

logger = logging.getLogger(__name__)

VALID_STRUCTURE_STYLES = frozenset(
    {
        "topic_blocks",
        "timeline",
        "steps",
        "qa",
        "prose",
        "comparison",
        "general",
    }
)

VALID_SECTION_FORMATS = frozenset({"prose", "bullets", "steps", "qa"})

STRUCTURE_TO_SECTION_FORMAT = {
    "topic_blocks": "bullets",
    "timeline": "bullets",
    "steps": "steps",
    "qa": "qa",
    "prose": "prose",
    "comparison": "bullets",
    "general": "bullets",
}


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
    timeout = httpx.Timeout(300.0, connect=30.0)
    return OpenAI(api_key=api_key, base_url=DEEPSEEK_BASE_URL, timeout=timeout)


def _friendly_api_error(exc: Exception) -> str:
    msg = str(exc)
    lower = msg.lower()
    if "401" in msg or "authentication" in lower or "invalid api key" in lower:
        return (
            "DeepSeek API Key 无效或已过期，请在「模型与 API 设置」中重新填写正确的 sk- 密钥。"
        )
    if "503" in msg or "service is too busy" in lower or "service_unavailable" in lower:
        return (
            "DeepSeek 服务繁忙（503），请稍后重试或暂时在设置中改用 deepseek-chat。"
        )
    if isinstance(exc, APITimeoutError) or "timed out" in lower:
        return "DeepSeek 请求超时，请检查网络或稍后重试。"
    if isinstance(exc, APIConnectionError):
        return "无法连接 DeepSeek API，请检查网络能否访问 api.deepseek.com。"
    return msg


def _build_notes_prompt() -> str:
    scenarios = list_scenarios_for_prompt()
    styles = list_summary_styles_for_prompt()

    return f"""你是视频学习笔记助手。用户会给你一整段语音转写纯文本（Whisper 输出，可能有同音错字、术语误听）。

请按顺序完成以下工作（仍只返回一个 JSON 对象）：

**第一步：推断视频背景**
- 根据全文推断视频主题、行业/领域、受众与内容形态
- 写入 meta（含 video_type、summary_style、industry、background_summary、structure_style、confidence、type_reason）
- video_type 从下列选一项：
{scenarios}
- summary_style 从下列选一项：
{styles}
- structure_style 根据内容自选笔记组织方式（字符串 id）：
  - topic_blocks：主题块 + 要点（教程、知识讲解）→ 建议 section_format=bullets
  - timeline：时间线/事件序列（资讯、复盘）→ 建议 section_format=bullets
  - steps：操作步骤（实操、演示）→ section_format=steps
  - qa：问答/访谈结构 → section_format=qa
  - prose：连贯段落（叙事、vlog）→ section_format=prose
  - comparison：对比/优劣分析（评测）→ 建议 section_format=bullets
  - general：以上都不合适时 → section_format=bullets
- section_format：全片唯一的段落写法（prose | bullets | steps | qa），写入 meta，**所有 sections 必须与之一致**
- background_summary：1–2 句说明视频在讲什么、处于什么行业语境（≤120 字）

**第二步：生成笔记**
- 使用 meta.section_format 作为**全片唯一**段落格式；**禁止**不同 section 使用不同 format（不得混用 bullets / prose / qa / steps）
- sections：3–8 段，按时间顺序**完整覆盖**全片（首尾相接，最后一段 end_time 应接近转写结束时间）
- 每段 section 字段（结构必须完全一致）：
  - title、start_time、end_time（秒，一位小数）
  - format：必须与 meta.section_format **相同**
  - 按 format 只填对应字段（不要混用）：
    - prose → content（1–3 段连贯文字，不要 lead+points 混搭）
    - bullets → points（2–5 条字符串，不要加「总/分」前缀）
    - steps → steps（有序步骤字符串数组）
    - qa → qa（[{{"q":"…","a":"…"}}] 数组）
  - **不要**使用 lead 字段（保持各段版式一致）
- overview：80–200 字全片概括，语气与 section_format 协调（bullets 类可用紧凑陈述，prose 类可用连贯段落）

禁止：复述口水话、编造转写中没有的信息、使用「总：」「分：」等标签前缀。

只返回 JSON（不要 markdown 代码块外的文字）：
{{
  "meta": {{
    "video_type": "general",
    "summary_style": "general",
    "industry": "",
    "background_summary": "",
    "structure_style": "topic_blocks",
    "section_format": "bullets",
    "confidence": 0.8,
    "type_reason": ""
  }},
  "overview": "……",
  "sections": [
    {{
      "title": "……",
      "start_time": 0.0,
      "end_time": 120.0,
      "format": "bullets",
      "points": ["……"]
    }}
  ]
}}"""


def _build_messages(transcript_text: str) -> list[dict]:
    body = transcript_text[:60000]
    intro = (
        "以下是一整段视频语音转写纯文本（Whisper）。"
        "请：1 推断背景  2 生成笔记。\n\n"
        "【转写全文】\n"
    )
    return [
        {"role": "system", "content": _build_notes_prompt()},
        {
            "role": "user",
            "content": intro + body + "\n\n请输出 json 对象（仅 JSON）。",
        },
    ]


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


def generate_notes(
    transcript_text: str,
    segments: list[dict] | None = None,
) -> dict:
    """生成 { overview, sections, meta }。"""
    client = get_client()
    model = get_deepseek_model()
    messages = _build_messages(transcript_text)

    create_kwargs = {
        "model": model,
        "messages": messages,
        "response_format": {"type": "json_object"},
    }

    seg_count = len(segments or [])
    logger.info(
        "DeepSeek 请求: model=%s, 转写约 %s 字, 本地句段 %s 条",
        model,
        len(transcript_text),
        seg_count,
    )

    try:
        resp = client.chat.completions.create(**create_kwargs)
    except APIStatusError as e:
        raise ValueError(_friendly_api_error(e)) from e
    except (APITimeoutError, APIConnectionError) as e:
        raise ValueError(_friendly_api_error(e)) from e
    except Exception as e:
        raise ValueError(_friendly_api_error(e)) from e

    logger.info("DeepSeek 响应成功")

    if not resp.choices:
        raise ValueError("DeepSeek 返回为空（无 choices）")
    message = resp.choices[0].message
    content = (message.content or "").strip() or "{}"
    try:
        result = _parse_json_content(content)
    except (json.JSONDecodeError, IndexError):
        return {"overview": "", "sections": [], "meta": normalize_meta(None)}

    meta = _enrich_meta({}, result.get("meta"))
    overview = str(result.get("overview") or "").strip()

    sections_raw = result.get("sections")
    if not isinstance(sections_raw, list):
        for key in ("chapters", "result", "data"):
            if isinstance(result.get(key), list):
                sections_raw = result[key]
                break
        else:
            sections_raw = []

    end_t = _transcript_end(segments)
    uniform_fmt = _resolve_section_format(meta, sections_raw)
    meta["section_format"] = uniform_fmt
    sections = _normalize_sections(
        sections_raw, transcript_end=end_t, uniform_format=uniform_fmt
    )

    return {
        "overview": overview,
        "sections": sections,
        "meta": meta,
    }


def _resolve_section_format(meta: dict, sections_raw: list) -> str:
    fmt = str(meta.get("section_format") or "").strip().lower()
    if fmt in VALID_SECTION_FORMATS:
        return fmt
    for raw in sections_raw:
        if isinstance(raw, dict):
            cand = str(raw.get("format") or "").strip().lower()
            if cand in VALID_SECTION_FORMATS:
                return cand
    ss = str(meta.get("structure_style") or "general").strip()
    return STRUCTURE_TO_SECTION_FORMAT.get(ss, "bullets")


def _collect_section_lines(raw: dict) -> list[str]:
    lines: list[str] = []
    lead = _strip_note_label(str(raw.get("lead") or ""))
    if lead:
        lines.append(lead)
    content = _strip_note_label(str(raw.get("content") or ""))
    if content:
        lines.append(content)
    points_raw = raw.get("points") or []
    if isinstance(points_raw, str):
        if points_raw.strip():
            lines.append(_strip_note_label(points_raw))
    else:
        lines.extend(_strip_note_label(str(p)) for p in points_raw if str(p).strip())
    steps_raw = raw.get("steps") or []
    if isinstance(steps_raw, str):
        if steps_raw.strip():
            lines.append(_strip_note_label(steps_raw))
    else:
        lines.extend(_strip_note_label(str(s)) for s in steps_raw if str(s).strip())
    for item in raw.get("qa") or []:
        if not isinstance(item, dict):
            continue
        q = _strip_note_label(str(item.get("q") or item.get("question") or ""))
        a = _strip_note_label(str(item.get("a") or item.get("answer") or ""))
        if q:
            lines.append(q)
        if a:
            lines.append(a)
    return [ln for ln in lines if ln]


def _normalize_sections(
    sections: list,
    transcript_end: float = 0.0,
    *,
    uniform_format: str = "bullets",
) -> list[dict]:
    fmt = uniform_format if uniform_format in VALID_SECTION_FORMATS else "bullets"
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

        sec: dict[str, Any] = {
            "title": title,
            "start_time": start,
            "end_time": end,
            "format": fmt,
        }

        lines = _collect_section_lines(raw)
        if fmt == "prose":
            if lines:
                sec["content"] = "\n".join(lines)
        elif fmt == "steps":
            if lines:
                sec["steps"] = lines
        elif fmt == "qa":
            qa_list = []
            if isinstance(raw.get("qa"), list) and raw.get("qa"):
                for item in raw["qa"]:
                    if not isinstance(item, dict):
                        continue
                    q = _strip_note_label(str(item.get("q") or item.get("question") or ""))
                    a = _strip_note_label(str(item.get("a") or item.get("answer") or ""))
                    if q or a:
                        qa_list.append({"q": q, "a": a})
            if not qa_list and lines:
                for ln in lines:
                    qa_list.append({"q": ln, "a": ""})
            if qa_list:
                sec["qa"] = qa_list
        else:
            if lines:
                sec["points"] = lines

        if sec.get("content") or sec.get("points") or sec.get("steps") or sec.get("qa"):
            out.append(sec)

    if out and transcript_end > 0:
        out[-1]["end_time"] = max(float(out[-1]["end_time"]), round(transcript_end, 1))

    return out


def _transcript_end(segments: list[dict] | None) -> float:
    if not segments:
        return 0.0
    try:
        return max(float(s.get("end_time", 0)) for s in segments)
    except (TypeError, ValueError):
        return 0.0


def _enrich_meta(meta: dict, raw: dict | None) -> dict:
    meta = normalize_meta(raw if isinstance(raw, dict) else meta)
    if isinstance(raw, dict):
        bg = str(raw.get("background_summary") or "").strip()[:200]
        if bg:
            meta["background_summary"] = bg
        ss = str(raw.get("structure_style") or "general").strip()
        if ss in VALID_STRUCTURE_STYLES:
            meta["structure_style"] = ss
        else:
            meta["structure_style"] = "general"
        sf = str(raw.get("section_format") or "").strip().lower()
        if sf in VALID_SECTION_FORMATS:
            meta["section_format"] = sf
        elif meta.get("structure_style") in STRUCTURE_TO_SECTION_FORMAT:
            meta["section_format"] = STRUCTURE_TO_SECTION_FORMAT[meta["structure_style"]]
        else:
            meta["section_format"] = "bullets"
    return meta


def analyze_chapters(transcript_text: str) -> list[dict]:
    notes = generate_notes(transcript_text)
    return notes["sections"]


def generate_summary(transcript_text: str) -> str:
    notes = generate_notes(transcript_text)
    return notes["overview"]
