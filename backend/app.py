"""SumVideo FastAPI 后端入口"""

from core.hf_cache import setup_hf_hub_cache

setup_hf_hub_cache()

import os
import uuid
import hashlib
import asyncio
import shutil
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
import uvicorn

import config
from core.transcriber import transcribe
from core.summarizer import generate_notes
from core.settings_store import (
    is_ready,
    is_api_configured,
    get_api_key,
    get_whisper_model,
    get_deepseek_model,
    has_invalid_stored_api_key,
    mask_api_key,
    is_valid_api_key,
    save_settings,
    clear_all_settings,
)
import config as app_config
from core.whisper_models import (
    get_recommended_model_id,
    list_options_for_api,
    options_compatible_with_platform,
    platform_label,
    current_platform,
)
from core.model_download import (
    get_download_hint,
    get_download_status,
    is_model_cached,
    start_download,
)
from core.settings_store import is_settings_ready, is_fully_ready
from core.storage_cleanup import (
    find_video_path,
    on_processing_failed,
    purge_video_record,
    run_storage_cleanup,
)
from db.database import (
    init_db,
    insert_video,
    update_status,
    update_result,
    update_error,
    get_video,
    find_by_hash,
    list_ids_by_hash,
    get_all_history,
)

app = FastAPI(title="SumVideo", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 确保存储目录存在
UPLOAD_DIR = Path(config.UPLOAD_DIR)
AUDIO_DIR = Path(config.AUDIO_DIR)
UPLOAD_DIR.mkdir(exist_ok=True)
AUDIO_DIR.mkdir(exist_ok=True)


VIDEO_EXTENSIONS = [".mp4", ".avi", ".mov", ".mkv", ".webm", ".flv", ".wmv", ".m4v", ".mpeg", ".mpg", ".3gp", ".ts"]

MEDIA_TYPES = {
    ".mp4": "video/mp4",
    ".m4v": "video/mp4",
    ".webm": "video/webm",
    ".mov": "video/quicktime",
    ".avi": "video/x-msvideo",
    ".mkv": "video/x-matroska",
    ".flv": "video/x-flv",
    ".wmv": "video/x-ms-wmv",
}


def normalize_transcript_segments(raw_segments: list) -> list[dict]:
    """统一 Whisper 分段为 { start_time, end_time, text }"""
    out = []
    for s in raw_segments or []:
        if not isinstance(s, dict):
            continue
        text = str(s.get("text") or "").strip()
        if not text:
            continue
        try:
            start = float(s.get("start_time", s.get("start", 0)))
            end = float(s.get("end_time", s.get("end", start)))
        except (TypeError, ValueError):
            continue
        out.append(
            {
                "start_time": round(start, 1),
                "end_time": round(max(end, start), 1),
                "text": text,
            }
        )
    return out


def compute_file_hash(file_path: str) -> str:
    """计算文件 SHA256 哈希"""
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


async def process_video(video_id: str, video_path: str, file_ext: str):
    """后台处理视频：转写 + 总结"""
    try:
        update_status(video_id, "processing", 5)

        # 步骤 1: 转写
        def progress_callback(percent: int, message: str = ""):
            # percent 为转写内部 10–90，与终端帧进度一致，写入数据库供前端轮询
            progress = min(80, max(5, percent))
            update_status(video_id, "processing", progress)

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: transcribe(video_path, get_whisper_model(), progress_callback),
        )

        transcript_text = result.get("text", "")
        whisper_segments = normalize_transcript_segments(result.get("segments", []))

        update_status(video_id, "processing", 82)

        def do_notes():
            return generate_notes(transcript_text)

        update_status(video_id, "processing", 88)
        notes = await loop.run_in_executor(None, do_notes)
        overview = notes.get("overview", "")
        sections = notes.get("sections") or []

        if not sections:
            sections = [
                {
                    "title": f"第 {i + 1} 段",
                    "start_time": round(s["start"], 1),
                    "end_time": round(s["end"], 1),
                    "lead": "",
                    "points": [s.get("text", "").strip()] if s.get("text") else [],
                }
                for i, s in enumerate(whisper_segments)
            ]

        update_status(video_id, "processing", 95)
        update_result(
            video_id,
            transcript_text,
            sections,
            overview,
            whisper_segments,
        )

    except Exception as e:
        error_msg = str(e)
        update_error(video_id, error_msg)
        on_processing_failed(video_id)


@app.on_event("startup")
def startup():
    init_db()
    run_storage_cleanup()


# ─── API 路由 ───


class SettingsBody(BaseModel):
    api_key: str | None = None  # 更新配置时可留空，保留已保存的 Key
    whisper_model: str
    deepseek_model: str = "deepseek-v4-flash"


@app.get("/api/settings")
def get_settings():
    """读取配置状态（API Key 仅返回掩码，供表单展示）"""
    whisper = get_whisper_model() or None
    model_ready = bool(whisper and is_model_cached(whisper))
    key = get_api_key()
    return {
        "ready": is_fully_ready(),
        "settings_ready": is_settings_ready(),
        "model_ready": model_ready,
        "api_configured": is_api_configured(),
        "api_key_masked": mask_api_key(key) if is_api_configured() else "",
        "api_key_invalid": has_invalid_stored_api_key(),
        "whisper_model": whisper,
        "deepseek_model": get_deepseek_model(),
        "platform": current_platform(),
        "platform_label": platform_label(),
        "recommended_whisper_model": get_recommended_model_id(),
        "whisper_options": list_options_for_api(),
        "deepseek_options": app_config.DEEPSEEK_MODEL_OPTIONS,
        "model_download_hint": get_download_hint(whisper) if whisper else None,
    }


@app.post("/api/settings")
def post_settings(body: SettingsBody):
    """保存首次/更新配置，完成后才可使用主功能"""
    submitted = (body.api_key or "").strip()
    if not submitted:
        if is_api_configured():
            key = get_api_key()
        else:
            raise HTTPException(400, "DeepSeek API Key 不能为空")
    elif submitted.replace("•", "").replace("●", "") == "" or "•••" in submitted:
        # 前端未修改掩码占位，保留已保存 Key
        if is_api_configured():
            key = get_api_key()
        else:
            raise HTTPException(400, "请填写有效的 DeepSeek API Key（sk- 开头）")
    else:
        key = submitted
    if not is_valid_api_key(key):
        raise HTTPException(
            400,
            "API Key 格式不正确：应以 sk- 开头，勿填写网址。请在 DeepSeek 开放平台复制密钥。",
        )
    if body.whisper_model not in app_config.WHISPER_MODEL_IDS:
        raise HTTPException(400, "无效的 Whisper 模型")
    if not options_compatible_with_platform(body.whisper_model):
        raise HTTPException(
            400,
            f"该 Whisper 模型不适用于当前系统（{platform_label()}），请选带「本机推荐」的项",
        )
    deepseek_model = body.deepseek_model
    deepseek_model = app_config.DEEPSEEK_MODEL_LEGACY_MAP.get(deepseek_model, deepseek_model)
    if deepseek_model not in app_config.DEEPSEEK_MODEL_IDS:
        raise HTTPException(400, "无效的 DeepSeek 模型")

    try:
        save_settings(key, body.whisper_model, deepseek_model)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    model_ready = is_model_cached(body.whisper_model)
    return {
        "settings_ready": True,
        "model_ready": model_ready,
        "ready": model_ready and is_settings_ready(),
        "message": "配置已保存" + ("，请继续下载所选 Whisper 模型" if not model_ready else ""),
    }


@app.get("/api/models/status")
def models_status():
    """当前所选模型的缓存与下载提示（需在设置中已选模型）"""
    if not is_settings_ready():
        raise HTTPException(400, "请先完成设置并选择 Whisper 模型")
    model_id = get_whisper_model()
    return {
        "model_id": model_id,
        "cached": is_model_cached(model_id),
        "hint": get_download_hint(model_id),
        "download": get_download_status(),
    }


@app.post("/api/models/download")
def models_download_start():
    """开始下载当前设置的 Whisper 模型（用户选完模型后再调用）"""
    if not is_settings_ready():
        raise HTTPException(400, "请先保存设置并选择 Whisper 模型")
    model_id = get_whisper_model()
    if is_model_cached(model_id):
        return {
            "started": False,
            "cached": True,
            "message": "模型已在本地，无需下载",
            "download": get_download_status(),
        }
    started = start_download(model_id)
    return {
        "started": started,
        "cached": False,
        "message": "已开始下载" if started else "下载任务进行中",
        "download": get_download_status(),
    }


@app.get("/api/models/download/status")
def models_download_progress():
    """轮询模型下载进度"""
    status = get_download_status()
    whisper = get_whisper_model() if is_settings_ready() else None
    return {
        **status,
        "model_ready": bool(whisper and is_model_cached(whisper)),
        "ready": is_fully_ready(),
    }


@app.delete("/api/settings")
def remove_settings():
    """清除全部本地配置，返回初始设置页"""
    clear_all_settings()
    return {"ready": False, "message": "已清除配置"}


@app.post("/api/upload")
async def upload_video(
    file: UploadFile = File(...),
    force: bool = Query(False, description="强制重新处理，忽略重复检测"),
):
    """上传视频文件，返回 task_id"""
    if not is_fully_ready():
        if not is_settings_ready():
            raise HTTPException(
                400,
                "请先完成设置：填写 DeepSeek API Key 并选择 Whisper 模型",
            )
        raise HTTPException(400, "请先下载所选 Whisper 模型后再上传视频")

    filename = file.filename or "upload.mp4"
    ext = Path(filename).suffix.lower()
    allowed = {
        ".mp4", ".avi", ".mov", ".mkv", ".webm", ".flv", ".wmv",
        ".m4v", ".mpeg", ".mpg", ".3gp", ".ts",
    }
    if not ext:
        raise HTTPException(400, "无法识别视频格式，请使用带扩展名的文件（如 .mp4 .mov .m4v）")
    if ext not in allowed:
        raise HTTPException(400, f"不支持的文件格式: {ext}")

    # 保存到临时文件
    temp_path = str(UPLOAD_DIR / f"temp_{uuid.uuid4().hex}{ext}")
    with open(temp_path, "wb") as f:
        content = await file.read()
        f.write(content)

    # 计算 hash
    file_hash = compute_file_hash(temp_path)

    # 查重（force=true 时跳过弹窗，但会替换同哈希的旧记录）
    existing = None if force else find_by_hash(file_hash)
    if existing:
        os.remove(temp_path)
        return {
            "duplicate": True,
            "existing": {
                "id": existing["id"],
                "filename": existing["filename"],
                "created_at": existing["created_at"],
            },
            "message": "该视频已处理过，是否使用已有结果？",
        }

    if force:
        for old_id in list_ids_by_hash(file_hash):
            purge_video_record(old_id)

    video_id = uuid.uuid4().hex
    insert_video(video_id, filename, file_hash)

    # 重命名为正式文件名
    final_path = str(UPLOAD_DIR / f"{video_id}{ext}")
    shutil.move(temp_path, final_path)

    # 后台启动处理
    asyncio.create_task(process_video(video_id, final_path, ext))

    return {"task_id": video_id, "duplicate": False}


def _progress_message(progress: float, status: str) -> str:
    if status != "processing":
        return ""
    if progress < 15:
        return "准备转写…"
    if progress < 82:
        return "正在 Whisper 转写…"
    if progress < 100:
        return "正在生成 AI 笔记…"
    return ""


@app.get("/api/video/{video_id}")
async def stream_video(video_id: str):
    """播放已上传的视频（处理完成后仍保留在 uploads 目录）"""
    path = find_video_path(video_id)
    if path is None:
        raise HTTPException(404, "视频文件不存在")
    media_type = MEDIA_TYPES.get(path.suffix.lower(), "application/octet-stream")
    return FileResponse(path, media_type=media_type, filename=path.name)


@app.get("/api/status/{task_id}")
async def get_status(task_id: str):
    """查询处理状态和结果"""
    video = get_video(task_id)
    if video is None:
        raise HTTPException(404, "任务不存在")

    prog = float(video["progress"] or 0)
    return {
        "id": video["id"],
        "filename": video["filename"],
        "status": video["status"],
        "progress": prog,
        "progress_message": _progress_message(prog, video["status"]),
        "transcript": video.get("transcript"),
        "transcript_segments": video.get("transcript_segments"),
        "chapters": video.get("chapters"),
        "summary": video.get("summary"),
        "created_at": video["created_at"],
        "updated_at": video.get("updated_at"),
    }


@app.get("/api/history")
async def get_history():
    """获取历史记录列表"""
    return get_all_history()


@app.delete("/api/history/{video_id}")
async def delete_history(video_id: str):
    """删除历史记录"""
    video = get_video(video_id)
    if video is None:
        raise HTTPException(404, "记录不存在")

    purge_video_record(video_id)
    return {"message": "已删除"}


@app.post("/api/retry/{video_id}")
async def retry_video(video_id: str):
    """重新处理视频"""
    if not is_ready():
        raise HTTPException(400, "请先完成初始配置")

    video = get_video(video_id)
    if video is None:
        raise HTTPException(404, "记录不存在")

    # 检查上传文件是否还存在
    found = find_video_path(video_id)
    if found is not None:
        video_path = str(found)
    else:
        raise HTTPException(400, "视频文件已丢失，无法重新处理")

    update_status(video_id, "pending", 0)
    asyncio.create_task(process_video(video_id, video_path, Path(video_path).suffix))

    return {"message": "已重新开始处理", "task_id": video_id}


if __name__ == "__main__":
    uvicorn.run(app, host=config.HOST, port=config.PORT)
