"""SQLite 历史记录管理"""

import sqlite3
import json
import os
from datetime import datetime, timedelta

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "sumvideo.db")


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
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
    conn.commit()
    conn.close()


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, col_type: str):
    cols = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")


def insert_video(video_id: str, filename: str, file_hash: str):
    conn = get_connection()
    conn.execute(
        "INSERT INTO videos (id, filename, file_hash) VALUES (?, ?, ?)",
        (video_id, filename, file_hash),
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


def update_error(video_id: str, error_msg: str):
    conn = get_connection()
    conn.execute(
        "UPDATE videos SET status = 'error', progress = 0, transcript = ?, updated_at = datetime('now', 'localtime') WHERE id = ?",
        (error_msg, video_id),
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


def get_all_history() -> list[dict]:
    """按创建时间倒序；同一 file_hash 只保留最新一条（避免强制重传后历史重复）"""
    conn = get_connection()
    rows = conn.execute(
        """SELECT id, filename, file_hash, status, progress, created_at, updated_at
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


def mark_tasks_stale_as_error(max_age_hours: int) -> list[str]:
    """将长时间未更新的 pending/processing 标为 error，返回受影响的 id。"""
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
                    transcript = ?,
                    updated_at = datetime('now', 'localtime')
                WHERE id IN ({placeholders})""",
            ("处理超时或中断，请重新上传或从历史中删除", *ids),
        )
        conn.commit()
    conn.close()
    return ids
