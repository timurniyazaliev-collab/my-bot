"""SQLite storage for discovered videos, transcripts, storyboards and scripts.

One file, no server — good enough for a single-user internal tool.
"""

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS videos (
    video_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    channel_title TEXT NOT NULL,
    published_at TEXT NOT NULL,
    duration_seconds INTEGER NOT NULL,
    view_count INTEGER NOT NULL,
    like_count INTEGER NOT NULL,
    comment_count INTEGER NOT NULL,
    viral_score REAL NOT NULL,
    search_query TEXT,
    thumbnail_url TEXT,
    fetched_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS transcripts (
    video_id TEXT PRIMARY KEY REFERENCES videos(video_id),
    text TEXT NOT NULL,
    segments_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS storyboards (
    video_id TEXT PRIMARY KEY REFERENCES videos(video_id),
    scenes_json TEXT NOT NULL,
    hook_analysis TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS scripts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id TEXT REFERENCES videos(video_id),
    content TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


@contextmanager
def get_conn():
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript(SCHEMA)


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def upsert_video(video: dict) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO videos (
                video_id, title, channel_title, published_at, duration_seconds,
                view_count, like_count, comment_count, viral_score,
                search_query, thumbnail_url, fetched_at
            ) VALUES (:video_id, :title, :channel_title, :published_at,
                :duration_seconds, :view_count, :like_count, :comment_count,
                :viral_score, :search_query, :thumbnail_url, :fetched_at)
            ON CONFLICT(video_id) DO UPDATE SET
                title=excluded.title,
                channel_title=excluded.channel_title,
                view_count=excluded.view_count,
                like_count=excluded.like_count,
                comment_count=excluded.comment_count,
                viral_score=excluded.viral_score,
                search_query=excluded.search_query,
                fetched_at=excluded.fetched_at
            """,
            {**video, "fetched_at": now()},
        )


def list_videos(limit: int = 50) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM videos ORDER BY viral_score DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]


def get_video(video_id: str) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM videos WHERE video_id = ?", (video_id,)
        ).fetchone()
        return dict(row) if row else None


def save_transcript(video_id: str, text: str, segments: list[dict]) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO transcripts (video_id, text, segments_json, created_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(video_id) DO UPDATE SET
                text=excluded.text, segments_json=excluded.segments_json,
                created_at=excluded.created_at
            """,
            (video_id, text, json.dumps(segments, ensure_ascii=False), now()),
        )


def get_transcript(video_id: str) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM transcripts WHERE video_id = ?", (video_id,)
        ).fetchone()
        if not row:
            return None
        data = dict(row)
        data["segments"] = json.loads(data.pop("segments_json"))
        return data


def save_storyboard(video_id: str, scenes: list[dict], hook_analysis: str) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO storyboards (video_id, scenes_json, hook_analysis, created_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(video_id) DO UPDATE SET
                scenes_json=excluded.scenes_json,
                hook_analysis=excluded.hook_analysis,
                created_at=excluded.created_at
            """,
            (video_id, json.dumps(scenes, ensure_ascii=False), hook_analysis, now()),
        )


def get_storyboard(video_id: str) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM storyboards WHERE video_id = ?", (video_id,)
        ).fetchone()
        if not row:
            return None
        data = dict(row)
        data["scenes"] = json.loads(data.pop("scenes_json"))
        return data


def save_script(video_id: str, content: str) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO scripts (video_id, content, created_at) VALUES (?, ?, ?)",
            (video_id, content, now()),
        )
        return cur.lastrowid


def list_scripts(video_id: str) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM scripts WHERE video_id = ? ORDER BY id DESC", (video_id,)
        ).fetchall()
        return [dict(r) for r in rows]
