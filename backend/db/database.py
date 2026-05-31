"""SQLite 历史记录管理"""

import sqlite3
import json
from datetime import datetime, timedelta

from core.paths import db_path


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path()), timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


def init_db():
    conn = get_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS videos (
            id TEXT PRIMARY KEY,
            filename TEXT NOT NULL,
            file_hash TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            progress REAL DEFAULT 0,
            transcript TEXT,
            chapters TEXT,
            summary TEXT,
            created_at TEXT DEFAULT (datetime('now', 'localtime')),
            updated_at TEXT DEFAULT (datetime('now', 'localtime'))
        )
    """)
    _ensure_column(conn, "videos", "transcript_segments", "TEXT")
    _ensure_column(conn, "videos", "source_path", "TEXT")
    _ensure_column(conn, "videos", "source_url", "TEXT")
    _ensure_column(conn, "videos", "error_message", "TEXT")
    conn.commit()
    conn.close()


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, col_type: str):
    cols = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")


def insert_video(
    video_id: str,
    filename: str,
    file_hash: str,
    source_path: str | None = None,
    source_url: str | None = None,
):
    conn = get_connection()
    conn.execute(
        "INSERT INTO videos (id, filename, file_hash, source_path, source_url) VALUES (?, ?, ?, ?, ?)",
        (video_id, filename, file_hash, source_path, source_url),
    )
    conn.commit()
    conn.close()


def update_file_hash(video_id: str, file_hash: str) -> None:
    conn = get_connection()
    conn.execute(
        "UPDATE videos SET file_hash = ?, updated_at = datetime('now', 'localtime') WHERE id = ?",
        (file_hash, video_id),
    )
    conn.commit()
    conn.close()


def update_filename(video_id: str, filename: str) -> None:
    conn = get_connection()
    conn.execute(
        "UPDATE videos SET filename = ?, updated_at = datetime('now', 'localtime') WHERE id = ?",
        (filename, video_id),
    )
    conn.commit()
    conn.close()


def update_status(video_id: str, status: str, progress: float = 0):
    conn = get_connection()
    conn.execute(
        "UPDATE videos SET status = ?, progress = ?, updated_at = datetime('now', 'localtime') WHERE id = ?",
        (status, progress, video_id),
    )
    conn.commit()
    conn.close()


def update_transcript_progress(
    video_id: str,
    transcript: str,
    transcript_segments: list | None = None,
    progress: float = 82,
):
    """转写完成、笔记未生成前写入，避免 88% 僵尸时连转写都看不到。"""
    conn = get_connection()
    seg_json = (
        json.dumps(transcript_segments, ensure_ascii=False)
        if transcript_segments
        else None
    )
    conn.execute(
        """UPDATE videos
           SET status = 'processing', progress = ?, transcript = ?,
               transcript_segments = ?, updated_at = datetime('now', 'localtime')
           WHERE id = ?""",
        (progress, transcript, seg_json, video_id),
    )
    conn.commit()
    conn.close()


def update_result(
    video_id: str,
    transcript: str,
    chapters: list,
    summary: str,
    transcript_segments: list | None = None,
):
    conn = get_connection()
    seg_json = (
        json.dumps(transcript_segments, ensure_ascii=False)
        if transcript_segments
        else None
    )
    conn.execute(
        """UPDATE videos
           SET status = 'done', progress = 100, transcript = ?,
               chapters = ?, summary = ?, transcript_segments = ?,
               updated_at = datetime('now', 'localtime')
           WHERE id = ?""",
        (transcript, json.dumps(chapters, ensure_ascii=False), summary, seg_json, video_id),
    )
    conn.commit()
    conn.close()


def update_error(video_id: str, error_msg: str, *, preserve_transcript: bool = False):
    conn = get_connection()
    if preserve_transcript:
        conn.execute(
            """UPDATE videos
               SET status = 'error', progress = 0, error_message = ?,
                   updated_at = datetime('now', 'localtime')
               WHERE id = ?""",
            (error_msg, video_id),
        )
    else:
        conn.execute(
            """UPDATE videos
               SET status = 'error', progress = 0, error_message = ?, transcript = ?,
                   updated_at = datetime('now', 'localtime')
               WHERE id = ?""",
            (error_msg, error_msg, video_id),
        )
    conn.commit()
    conn.close()


def prepare_retry(video_id: str, *, notes_only: bool) -> None:
    """重试前清理错误态；notes_only 时保留 transcript/segments。"""
    conn = get_connection()
    progress = 82.0 if notes_only else 5.0
    if notes_only:
        conn.execute(
            """UPDATE videos
               SET status = 'processing', progress = ?, error_message = NULL,
                   chapters = NULL, summary = NULL,
                   updated_at = datetime('now', 'localtime')
               WHERE id = ?""",
            (progress, video_id),
        )
    else:
        conn.execute(
            """UPDATE videos
               SET status = 'processing', progress = ?, error_message = NULL,
                   transcript = NULL, transcript_segments = NULL,
                   chapters = NULL, summary = NULL,
                   updated_at = datetime('now', 'localtime')
               WHERE id = ?""",
            (progress, video_id),
        )
    conn.commit()
    conn.close()


def get_video(video_id: str) -> dict | None:
    conn = get_connection()
    row = conn.execute("SELECT * FROM videos WHERE id = ?", (video_id,)).fetchone()
    conn.close()
    if row is None:
        return None
    result = dict(row)
    if result.get("chapters"):
        result["chapters"] = json.loads(result["chapters"])
    if result.get("transcript_segments"):
        result["transcript_segments"] = json.loads(result["transcript_segments"])
    return result


def list_ids_by_hash(file_hash: str) -> list[str]:
    """同一文件哈希对应的全部任务 id（任意状态）"""
    conn = get_connection()
    rows = conn.execute(
        "SELECT id FROM videos WHERE file_hash = ? ORDER BY created_at DESC",
        (file_hash,),
    ).fetchall()
    conn.close()
    return [r[0] for r in rows]


def find_by_hash(file_hash: str) -> dict | None:
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM videos WHERE file_hash = ? AND status = 'done' ORDER BY created_at DESC LIMIT 1",
        (file_hash,),
    ).fetchone()
    conn.close()
    if row is None:
        return None
    result = dict(row)
    if result.get("chapters"):
        result["chapters"] = json.loads(result["chapters"])
    if result.get("transcript_segments"):
        result["transcript_segments"] = json.loads(result["transcript_segments"])
    return result


def find_by_source_url(source_url: str) -> dict | None:
    conn = get_connection()
    row = conn.execute(
        """SELECT * FROM videos WHERE source_url = ? AND status = 'done'
           ORDER BY created_at DESC LIMIT 1""",
        (source_url,),
    ).fetchone()
    conn.close()
    if row is None:
        return None
    result = dict(row)
    if result.get("chapters"):
        result["chapters"] = json.loads(result["chapters"])
    if result.get("transcript_segments"):
        result["transcript_segments"] = json.loads(result["transcript_segments"])
    return result


def list_ids_by_source_url(source_url: str) -> list[str]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT id FROM videos WHERE source_url = ? ORDER BY created_at DESC",
        (source_url,),
    ).fetchall()
    conn.close()
    return [r[0] for r in rows]


def get_all_history() -> list[dict]:
    """按创建时间倒序；同一 file_hash 只保留最新一条（避免强制重传后历史重复）"""
    conn = get_connection()
    rows = conn.execute(
        """SELECT id, filename, file_hash, status, progress, created_at, updated_at,
                  source_path
           FROM videos ORDER BY created_at DESC"""
    ).fetchall()
    conn.close()
    seen_hash: set[str] = set()
    out: list[dict] = []
    for row in rows:
        h = row["file_hash"]
        if h in seen_hash:
            continue
        seen_hash.add(h)
        item = dict(row)
        item.pop("file_hash", None)
        out.append(item)
    return out


def delete_video(video_id: str):
    conn = get_connection()
    conn.execute("DELETE FROM videos WHERE id = ?", (video_id,))
    conn.commit()
    conn.close()


def hashes_with_duplicates() -> list[str]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT file_hash FROM videos GROUP BY file_hash HAVING COUNT(*) > 1"
    ).fetchall()
    conn.close()
    return [r[0] for r in rows]


def list_all_video_ids() -> list[str]:
    conn = get_connection()
    rows = conn.execute("SELECT id FROM videos").fetchall()
    conn.close()
    return [r[0] for r in rows]


def list_video_ids_by_status(statuses: tuple[str, ...]) -> list[str]:
    if not statuses:
        return []
    placeholders = ",".join("?" for _ in statuses)
    conn = get_connection()
    rows = conn.execute(
        f"SELECT id FROM videos WHERE status IN ({placeholders})",
        statuses,
    ).fetchall()
    conn.close()
    return [r[0] for r in rows]


def mark_tasks_stale_as_error(max_age_hours: int, error_msg: str | None = None) -> list[str]:
    """将长时间未更新的 pending/processing 标为 error，返回受影响的 id。"""
    msg = error_msg or "处理超时或中断，请重新上传或从历史中删除"
    cutoff = (datetime.now() - timedelta(hours=max_age_hours)).strftime("%Y-%m-%d %H:%M:%S")
    conn = get_connection()
    rows = conn.execute(
        """SELECT id FROM videos
           WHERE status IN ('pending', 'processing')
           AND updated_at < ?""",
        (cutoff,),
    ).fetchall()
    ids = [r[0] for r in rows]
    if ids:
        placeholders = ",".join("?" for _ in ids)
        conn.execute(
            f"""UPDATE videos
                SET status = 'error',
                    progress = 0,
                    error_message = ?,
                    transcript = CASE
                        WHEN transcript_segments IS NOT NULL
                             AND transcript IS NOT NULL
                             AND length(trim(transcript)) > 50
                        THEN transcript
                        ELSE ?
                    END,
                    updated_at = datetime('now', 'localtime')
                WHERE id IN ({placeholders})""",
            (msg, msg, *ids),
        )
        conn.commit()
    conn.close()
    return ids


def mark_processing_stale_as_error(max_age_minutes: int, error_msg: str | None = None) -> list[str]:
    """仅处理 processing：用于后端 reload/崩溃后的 88% 僵尸任务。"""
    msg = error_msg or (
        "处理已中断（常见于开发时后端热重载）。请重新上传或从历史删除后重试。"
    )
    cutoff = (datetime.now() - timedelta(minutes=max_age_minutes)).strftime(
        "%Y-%m-%d %H:%M:%S"
    )
    conn = get_connection()
    rows = conn.execute(
        """SELECT id FROM videos WHERE status = 'processing' AND updated_at < ?""",
        (cutoff,),
    ).fetchall()
    ids = [r[0] for r in rows]
    if ids:
        placeholders = ",".join("?" for _ in ids)
        conn.execute(
            f"""UPDATE videos
                SET status = 'error',
                    progress = 0,
                    error_message = ?,
                    transcript = CASE
                        WHEN transcript_segments IS NOT NULL
                             AND transcript IS NOT NULL
                             AND length(trim(transcript)) > 50
                        THEN transcript
                        ELSE ?
                    END,
                    updated_at = datetime('now', 'localtime')
                WHERE id IN ({placeholders})""",
            (msg, msg, *ids),
        )
        conn.commit()
    conn.close()
    return ids
