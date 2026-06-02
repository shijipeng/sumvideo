"""SumVideo FastAPI 后端入口"""

from core.paths import init_data_paths

init_data_paths()

import config as app_config_module

app_config_module.refresh_path_config()

from core.hf_cache import get_hf_hub_cache_dir, setup_hf_hub_cache

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
from core.paths import get_data_dir
from core.settings_store import is_settings_ready, is_fully_ready
from core.storage_cleanup import (
    on_processing_failed,
    purge_video_record,
    run_storage_cleanup,
)
from core.frame_pipeline import get_thumbnail_path
from core.frame_stage import is_frame_stage_running, schedule_frame_stage
from core.scenarios import normalize_meta, scenario_label
from core.video_paths import resolve_video_path
from core.paths import upload_dir as paths_upload_dir
from core.task_resume import (
    video_error_message,
    video_has_resumable_transcript,
    video_has_saved_transcript,
)
from core.task_run_guard import (
    begin_video_run,
    is_pipeline_busy,
    is_stale_run,
    release_pipeline,
    try_acquire_pipeline,
)
from core.url_importer import (
    validate_url_safe,
    normalize_url,
    probe_video,
    download_video,
)
from core.subtitle_fetcher import try_fetch_subtitles, SubtitleResult
from db.database import (
    init_db,
    insert_video,
    update_status,
    update_transcript_progress,
    update_result,
    update_error,
    prepare_retry,
    prepare_retry_frames_only,
    get_video,
    find_by_hash,
    find_by_source_url,
    list_ids_by_hash,
    list_ids_by_source_url,
    update_file_hash,
    update_filename,
    get_all_history,
    mark_processing_stale_as_error,
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
UPLOAD_DIR = paths_upload_dir()
AUDIO_DIR = Path(config.AUDIO_DIR)
UPLOAD_DIR.mkdir(exist_ok=True)
AUDIO_DIR.mkdir(parents=True, exist_ok=True)


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


def _schedule_process_video(
    video_id: str,
    video_path: str,
    file_ext: str,
    *,
    notes_only: bool = False,
    min_progress: float = 5,
) -> None:
    run_id = begin_video_run(video_id)
    asyncio.create_task(
        process_video(
            video_id,
            video_path,
            file_ext,
            notes_only=notes_only,
            min_progress=min_progress,
            run_id=run_id,
        )
    )


def compute_file_hash(file_path: str) -> str:
    """计算文件 SHA256 哈希"""
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def _pending_url_hash(normalized_url: str) -> str:
    return "pending:" + hashlib.sha256(normalized_url.encode("utf-8")).hexdigest()


def _touch_progress(video_id: str, run_id: int, progress: float) -> None:
    """仅当前 run 有效时更新进度，避免过期 Whisper 任务把进度写回去。"""
    if is_stale_run(video_id, run_id):
        return
    update_status(video_id, "processing", progress)


def _reject_if_video_pipeline_busy(video: dict) -> None:
    """转写/笔记 pipeline 运行中则拒绝再次发起。"""
    vid = video["id"]
    if video.get("status") in ("processing", "pending"):
        raise HTTPException(
            409,
            "该视频正在处理中（转写或 AI 笔记），请等待当前任务完成后再试",
        )
    if is_pipeline_busy(vid):
        raise HTTPException(
            409,
            "该视频已有处理任务在运行，请稍候",
        )


async def _run_notes_stage(
    video_id: str,
    transcript_text: str,
    whisper_segments: list[dict],
    loop: asyncio.AbstractEventLoop,
    notes_timeout: float,
    *,
    run_id: int,
):
    """转写完成后或断点续跑：生成笔记并写入结果。"""
    import logging

    log = logging.getLogger("sumvideo.process")

    if is_stale_run(video_id, run_id):
        log.warning("任务 %s 笔记阶段已过期 (run_id=%s)，跳过写入", video_id, run_id)
        return

    def do_notes():
        notes_log = logging.getLogger("sumvideo.notes")
        notes_log.info(
            "开始 DeepSeek 笔记生成，转写约 %s 字，句段 %s 条",
            len(transcript_text),
            len(whisper_segments),
        )
        try:
            return generate_notes(transcript_text, whisper_segments)
        finally:
            notes_log.info("DeepSeek 笔记生成结束")

    _touch_progress(video_id, run_id, 88)
    log.info("任务 %s 进入笔记阶段（88%%）", video_id)
    if is_stale_run(video_id, run_id):
        log.warning("任务 %s 笔记阶段开始前 run 已过期 (run_id=%s)", video_id, run_id)
        return
    _touch_progress(video_id, run_id, 89)
    log.info("任务 %s 正在请求 DeepSeek（89%%）", video_id)
    try:
        notes = await asyncio.wait_for(
            loop.run_in_executor(None, do_notes),
            timeout=notes_timeout,
        )
    except asyncio.TimeoutError:
        raise TimeoutError(
            f"笔记生成超过 {int(notes_timeout)} 秒仍未完成，请检查网络或稍后重试"
        ) from None

    if is_stale_run(video_id, run_id):
        log.warning("任务 %s DeepSeek 返回后 run 已过期 (run_id=%s)，丢弃结果", video_id, run_id)
        return

    overview = notes.get("overview", "")
    sections = notes.get("sections") or []
    meta = notes.get("meta") or {}

    if not sections:
        sections = [
            {
                "title": f"第 {i + 1} 段",
                "start_time": round(s["start_time"], 1),
                "end_time": round(s["end_time"], 1),
                "lead": "",
                "points": [s.get("text", "").strip()] if s.get("text") else [],
            }
            for i, s in enumerate(whisper_segments)
        ]

    _touch_progress(video_id, run_id, 95)
    video_path = resolve_video_path(video_id)
    frame_status = "pending" if video_path else "skipped"
    update_result(
        video_id,
        transcript_text,
        sections,
        overview,
        whisper_segments,
        notes_meta=meta,
        frame_status=frame_status,
    )
    if video_path:
        schedule_frame_stage(video_id)


async def process_video(
    video_id: str,
    video_path: str,
    file_ext: str,
    *,
    notes_only: bool = False,
    min_progress: float = 5,
    run_id: int = 0,
):
    """后台处理视频：转写 + 总结；notes_only 时跳过 Whisper 仅用已存转写。"""
    import logging

    log = logging.getLogger("sumvideo.process")
    loop = asyncio.get_running_loop()
    notes_timeout = float(getattr(config, "NOTES_STAGE_TIMEOUT_SEC", 360))
    transcript_saved = False

    log.info(
        "任务 %s 开始 process_video notes_only=%s run_id=%s path=%s",
        video_id,
        notes_only,
        run_id,
        video_path or "(empty)",
    )

    try:
        if is_stale_run(video_id, run_id):
            log.warning("任务 %s 启动即过期 (run_id=%s)，中止", video_id, run_id)
            return

        if notes_only:
            row = get_video(video_id)
            if not row or not video_has_saved_transcript(row):
                raise ValueError("无已保存的转写，请使用「从头重新处理」")
            transcript_text = (row.get("transcript") or "").strip()
            whisper_segments = normalize_transcript_segments(
                row.get("transcript_segments") or []
            )
            transcript_saved = True
            _touch_progress(video_id, run_id, 82)
            log.info("任务 %s 断点续跑：跳过转写，直接生成笔记", video_id)
        else:
            _touch_progress(video_id, run_id, min_progress)

            def progress_callback(percent: int, message: str = ""):
                progress = min(80, max(min_progress, percent))

                def _write():
                    _touch_progress(video_id, run_id, progress)

                loop.call_soon_threadsafe(_write)

            result = await loop.run_in_executor(
                None,
                lambda: transcribe(video_path, get_whisper_model(), progress_callback),
            )

            transcript_text = result.get("text", "")
            whisper_segments = normalize_transcript_segments(result.get("segments", []))

            if is_stale_run(video_id, run_id):
                log.warning(
                    "任务 %s Whisper 完成但 run 已过期 (run_id=%s)，不写库 (%s 条)",
                    video_id,
                    run_id,
                    len(whisper_segments),
                )
                return

            update_transcript_progress(
                video_id, transcript_text, whisper_segments, progress=82
            )
            transcript_saved = True
            log.info(
                "任务 %s Whisper 落库 %s 条 (run_id=%s)",
                video_id,
                len(whisper_segments),
                run_id,
            )

        await _run_notes_stage(
            video_id,
            transcript_text,
            whisper_segments,
            loop,
            notes_timeout,
            run_id=run_id,
        )

    except BrokenPipeError:
        error_msg = (
            "转写进程输出管道中断（常见于后端被管道命令启动）。"
            "请用 npm run backend 或 scripts/start-backend.sh 重启后端后重试。"
        )
        update_error(video_id, error_msg, preserve_transcript=transcript_saved)
        on_processing_failed(video_id)
    except Exception as e:
        error_msg = str(e)
        if "Broken pipe" in error_msg or "BrokenPipeError" in type(e).__name__:
            error_msg = (
                "转写输出管道中断。请确保用 npm run backend 启动后端（不要接 | head 等管道），"
                f"然后重新上传或点「重新处理」。原始信息: {e}"
            )
        update_error(video_id, error_msg, preserve_transcript=transcript_saved)
        on_processing_failed(video_id)
    finally:
        release_pipeline(video_id, run_id)


async def _import_url_task(
    video_id: str,
    url: str,
    normalized_url: str,
    title: str,
    force: bool,
    *,
    run_id: int,
) -> None:
    import logging

    log = logging.getLogger("sumvideo.process")
    subs: SubtitleResult | None = None
    temp_path: str | None = None
    loop = asyncio.get_running_loop()
    notes_timeout = float(getattr(config, "NOTES_STAGE_TIMEOUT_SEC", 360))
    transcript_saved = False

    try:
        update_status(video_id, "processing", 2)
        subs = await loop.run_in_executor(None, lambda: try_fetch_subtitles(url))

        def on_dl_progress(p: float) -> None:
            update_status(video_id, "processing", p)

        update_status(video_id, "processing", 10)
        path = await loop.run_in_executor(
            None,
            lambda: download_video(url, UPLOAD_DIR, on_dl_progress),
        )
        temp_path = str(path)
        ext = path.suffix.lower()
        if ext not in ALLOWED_VIDEO_EXTENSIONS:
            ext = ".mp4"
            new_path = path.with_suffix(".mp4")
            if new_path != path:
                shutil.move(str(path), str(new_path))
                path = new_path
                temp_path = str(path)

        file_hash = compute_file_hash(temp_path)
        if not force:
            existing = find_by_hash(file_hash)
            if existing and existing["id"] != video_id:
                os.remove(temp_path)
                update_error(video_id, "与已有本地文件重复")
                on_processing_failed(video_id)
                return

        if force:
            for old_id in list_ids_by_hash(file_hash):
                if old_id != video_id:
                    purge_video_record(old_id)

        final_path = str(UPLOAD_DIR / f"{video_id}{ext}")
        shutil.move(temp_path, final_path)
        temp_path = None

        update_file_hash(video_id, file_hash)
        update_filename(video_id, title)

        if is_stale_run(video_id, run_id):
            log.warning("任务 %s URL 导入 run 已过期 (run_id=%s)，中止", video_id, run_id)
            return

        if subs:
            log.info(
                "任务 %s 使用在线字幕 %s 条，跳过 Whisper (run_id=%s)",
                video_id,
                len(subs.segments),
                run_id,
            )
            update_transcript_progress(
                video_id, subs.transcript_text, subs.segments, progress=82
            )
            transcript_saved = True
            await _run_notes_stage(
                video_id,
                subs.transcript_text,
                subs.segments,
                loop,
                notes_timeout,
                run_id=run_id,
            )
        else:
            await process_video(
                video_id, final_path, ext, min_progress=21, run_id=run_id
            )

    except Exception as e:
        if temp_path and os.path.isfile(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass
        update_error(video_id, str(e), preserve_transcript=transcript_saved)
        on_processing_failed(video_id)
    finally:
        release_pipeline(video_id, run_id)


@app.on_event("startup")
def startup():
    import logging

    init_db()
    stale_mins = int(getattr(config, "STALE_PROCESSING_MINUTES", 15))
    revived = mark_processing_stale_as_error(stale_mins)
    if revived:
        logging.getLogger(__name__).warning(
            "已将 %s 条长时间卡在 processing 的任务标为失败（多为后端热重载中断）",
            len(revived),
        )
    run_storage_cleanup()


# ─── API 路由 ───


class SettingsBody(BaseModel):
    api_key: str | None = None  # 更新配置时可留空，保留已保存的 Key
    whisper_model: str
    deepseek_model: str = "deepseek-v4-flash"


class ProcessPathBody(BaseModel):
    path: str
    force: bool = False


ALLOWED_VIDEO_EXTENSIONS = {
    ".mp4", ".avi", ".mov", ".mkv", ".webm", ".flv", ".wmv",
    ".m4v", ".mpeg", ".mpg", ".3gp", ".ts",
}


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
        "data_dir": str(get_data_dir()),
        "models_cache_dir": get_hf_hub_cache_dir(),
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
    model_ready = bool(whisper and is_model_cached(whisper))

    if (
        status.get("status") == "done"
        and model_ready
        and status.get("model_id") == whisper
    ):
        return {
            **status,
            "model_ready": True,
            "ready": is_fully_ready(),
        }

    downloading = (
        status.get("status") == "downloading"
        and status.get("model_id") == whisper
    )
    progress = int(status.get("progress") or 0)
    if downloading and progress < 95:
        return {**status, "model_ready": False, "ready": False}

    return {
        **status,
        "model_ready": model_ready,
        "ready": is_fully_ready() if model_ready else False,
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
    if not ext:
        raise HTTPException(400, "无法识别视频格式，请使用带扩展名的文件（如 .mp4 .mov .m4v）")
    if ext not in ALLOWED_VIDEO_EXTENSIONS:
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
    _schedule_process_video(video_id, final_path, ext)

    return {"task_id": video_id, "duplicate": False}


class ImportUrlBody(BaseModel):
    url: str
    force: bool = False


def _require_fully_ready_for_import():
    if not is_fully_ready():
        if not is_settings_ready():
            raise HTTPException(
                400,
                "请先完成设置：填写 DeepSeek API Key 并选择 Whisper 模型",
            )
        raise HTTPException(400, "请先下载所选 Whisper 模型后再导入视频")


@app.post("/api/import-url")
async def import_url_video(body: ImportUrlBody):
    """从在线 URL 导入：字幕优先跳过 Whisper，否则下载后 Whisper 转写。"""
    _require_fully_ready_for_import()

    raw = (body.url or "").strip()
    if not raw:
        raise HTTPException(400, "链接不能为空")

    try:
        validate_url_safe(raw)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except Exception as e:
        raise HTTPException(400, f"链接无效: {e}") from e

    normalized = normalize_url(raw)
    if not normalized:
        raise HTTPException(400, "链接无效")

    if not body.force:
        existing = find_by_source_url(normalized)
        if existing:
            if existing["status"] in ("processing", "pending") or is_pipeline_busy(
                existing["id"]
            ):
                raise HTTPException(
                    409,
                    "该链接视频正在处理中，请等待完成后再试",
                )
            return {
                "duplicate": True,
                "existing": {
                    "id": existing["id"],
                    "filename": existing["filename"],
                    "created_at": existing["created_at"],
                },
                "message": "该链接已处理过，是否使用已有结果？",
            }

    if body.force:
        for old_id in list_ids_by_source_url(normalized):
            purge_video_record(old_id)

    try:
        info = probe_video(raw)
        title = info.get("title") or "在线视频"
    except Exception as e:
        raise HTTPException(400, f"无法解析视频信息: {e}") from e

    video_id = uuid.uuid4().hex
    pending_hash = _pending_url_hash(normalized)
    insert_video(video_id, title, pending_hash, source_url=normalized)

    run_id = begin_video_run(video_id)
    asyncio.create_task(
        _import_url_task(video_id, raw, normalized, title, body.force, run_id=run_id)
    )

    return {"task_id": video_id, "duplicate": False}


@app.post("/api/process-path", deprecated=True)
async def process_path_video(_body: ProcessPathBody):
    """已废弃：请使用 POST /api/upload 上传视频到 uploads/。"""
    raise HTTPException(
        410,
        "此接口已废弃。桌面端请通过上传接口将视频复制到 uploads/ 后再处理。",
    )


def _progress_message(progress: float, status: str) -> str:
    if status != "processing":
        return ""
    if progress < 8:
        return "正在获取字幕…"
    if progress < 20:
        return "正在下载视频…"
    if progress < 88:
        return "正在 Whisper 转写…"
    if progress < 90:
        return "正在请求 DeepSeek 生成笔记（长视频可能需 2–5 分钟）…"
    if progress < 95:
        return "正在整理笔记…"
    return "正在保存结果…"


@app.get("/api/video/{video_id}")
async def stream_video(video_id: str):
    """播放视频：优先 uploads 副本，旧记录可回退 source_path。"""
    path = resolve_video_path(video_id)
    if path is None:
        video = get_video(video_id)
        if video and (video.get("source_path") or "").strip():
            raise HTTPException(
                404,
                "原视频文件已移动或删除，请在桌面重新选择文件",
            )
        raise HTTPException(404, "视频文件不存在")
    media_type = MEDIA_TYPES.get(path.suffix.lower(), "application/octet-stream")
    return FileResponse(path, media_type=media_type, filename=path.name)


@app.get("/api/video/{video_id}/thumb/{section_index}/{frame_index}")
async def get_section_thumbnail_multi(video_id: str, section_index: int, frame_index: int):
    """章节配图 JPEG（节内多图）。"""
    thumb = get_thumbnail_path(video_id, section_index, frame_index)
    if thumb is None:
        raise HTTPException(404, "配图不存在")
    return FileResponse(
        thumb,
        media_type="image/jpeg",
        filename=f"{section_index}_{frame_index}.jpg",
    )


@app.get("/api/video/{video_id}/thumb/{index}")
async def get_section_thumbnail_legacy(video_id: str, index: int):
    """章节配图 JPEG（兼容旧版单图路径）。"""
    thumb = get_thumbnail_path(video_id, index)
    if thumb is None:
        raise HTTPException(404, "配图不存在")
    return FileResponse(thumb, media_type="image/jpeg", filename=f"{index}.jpg")


@app.get("/api/status/{task_id}")
async def get_status(task_id: str):
    """查询处理状态和结果"""
    video = get_video(task_id)
    if video is None:
        raise HTTPException(404, "任务不存在")

    prog = float(video["progress"] or 0)
    err = video_error_message(video)
    resume = video["status"] == "error" and video_has_resumable_transcript(video)
    notes_meta = video.get("notes_meta")
    if notes_meta:
        notes_meta = normalize_meta(notes_meta)
    elif video.get("notes_meta") is None:
        notes_meta = None
    vt = (notes_meta or {}).get("video_type", "general")
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
        "notes_meta": notes_meta,
        "frame_status": video.get("frame_status") or "pending",
        "frame_progress_done": int(video.get("frame_progress_done") or 0),
        "frame_progress_total": int(video.get("frame_progress_total") or 0),
        "frame_error_message": video.get("frame_error_message"),
        "video_type_label": scenario_label(vt),
        "error_message": err,
        "resume_available": resume,
        "created_at": video["created_at"],
        "updated_at": video.get("updated_at"),
        "source_path": video.get("source_path"),
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
async def retry_video(
    video_id: str,
    from_stage: str = Query(
        "auto",
        description="auto=有转写则续跑笔记；notes_only=仅笔记；full=从头转写+笔记；frames_only=仅重跑配图",
    ),
):
    """重新处理；有已保存转写时可从笔记阶段继续；frames_only 仅异步配图。"""
    if not is_fully_ready():
        if not is_settings_ready():
            raise HTTPException(400, "请先完成设置")
        raise HTTPException(400, "请先下载所选 Whisper 模型")

    video = get_video(video_id)
    if video is None:
        raise HTTPException(404, "记录不存在")

    stage = (from_stage or "auto").strip().lower()
    if stage not in ("auto", "full", "notes_only", "frames_only"):
        raise HTTPException(400, "from_stage 须为 auto、full、notes_only 或 frames_only")

    if stage == "frames_only":
        if video["status"] != "done":
            raise HTTPException(400, "仅已完成的任务可单独重跑配图")
        if is_pipeline_busy(video_id):
            raise HTTPException(
                409,
                "该视频正在转写或生成笔记，请等待完成后再重跑配图",
            )
        if not video.get("chapters"):
            raise HTTPException(400, "无章节结构，无法生成配图")
        fs = video.get("frame_status") or "pending"
        if fs == "processing" or is_frame_stage_running(video_id):
            raise HTTPException(409, "配图正在生成中，请稍候")
        if resolve_video_path(video_id) is None:
            raise HTTPException(400, "视频文件不存在，无法生成配图")
        prepare_retry_frames_only(video_id)
        schedule_frame_stage(video_id)
        return {
            "message": "已开始重新生成配图（文字笔记不变）",
            "task_id": video_id,
            "resume_mode": "frames_only",
        }

    can_resume = video_has_resumable_transcript(video)
    if stage == "auto":
        notes_only = can_resume
    elif stage == "notes_only":
        if not video_has_saved_transcript(video):
            raise HTTPException(
                400,
                "无已保存的转写，无法重新生成笔记，请使用「从头重新处理」",
            )
        notes_only = True
    else:
        notes_only = False

    found = resolve_video_path(video_id)
    if found is not None:
        video_path = str(found)
    elif notes_only:
        video_path = ""
    else:
        if video and (video.get("source_path") or "").strip():
            raise HTTPException(
                400,
                "原视频文件已移动或删除，无法重新处理",
            )
        raise HTTPException(400, "上传的视频副本已丢失，请重新上传")

    _reject_if_video_pipeline_busy(video)
    run_id = try_acquire_pipeline(video_id)
    if run_id is None:
        raise HTTPException(409, "该视频已有处理任务在运行，请稍候")

    prepare_retry(video_id, notes_only=notes_only)
    asyncio.create_task(
        process_video(
            video_id,
            video_path,
            Path(video_path).suffix if video_path else ".mp4",
            notes_only=notes_only,
            run_id=run_id,
        )
    )

    if notes_only:
        msg = "已从笔记阶段继续（跳过转写）"
        mode = "notes_only"
    else:
        msg = "已从头重新处理（转写 + 笔记）"
        mode = "full"

    return {"message": msg, "task_id": video_id, "resume_mode": mode}


if __name__ == "__main__":
    uvicorn.run(app, host=config.HOST, port=config.PORT)
