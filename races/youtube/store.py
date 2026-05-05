"""SQLite store for YouTube analytics.

Schema:
    videos              one row per uploaded video (link to render context)
    metrics_daily       per-video x per-day metrics (views, watch time, CTR…)
    retention_curve     per-video x snapshot_date x elapsed_ratio_bucket

`cache/analytics.db` is gitignored (cache/ is in .gitignore).
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterable

SCHEMA = """
CREATE TABLE IF NOT EXISTS videos (
    video_id           TEXT PRIMARY KEY,
    channel            TEXT NOT NULL,
    uploaded_at        TEXT,
    published_at       TEXT,
    privacy_status     TEXT,
    title              TEXT,
    description        TEXT,
    duration_seconds   REAL,
    -- render-side context (NULL for backfilled videos with no manifest)
    manifest_path      TEXT,
    output_filename    TEXT,
    render_cfg_hash    TEXT,
    theme              TEXT,
    dataset_type       TEXT,
    dataset_indicator  TEXT,
    dataset_timeframe  TEXT,
    transforms         TEXT,         -- json
    narration_source   TEXT,
    narration_model    TEXT,
    narration_tone     TEXT,
    script_text        TEXT,
    registered_at      TEXT,         -- when we wrote this row
    last_pulled_at     TEXT,         -- last analytics refresh
    lifetime_impressions  INTEGER,
    lifetime_ctr          REAL
);

CREATE TABLE IF NOT EXISTS metrics_daily (
    video_id              TEXT NOT NULL,
    date                  TEXT NOT NULL,    -- YYYY-MM-DD
    views                 INTEGER,
    watch_time_minutes    REAL,
    avg_view_duration_s   REAL,
    avg_view_percentage   REAL,
    impressions           INTEGER,
    impression_ctr        REAL,
    likes                 INTEGER,
    dislikes              INTEGER,
    comments              INTEGER,
    shares                INTEGER,
    subscribers_gained    INTEGER,
    subscribers_lost      INTEGER,
    PRIMARY KEY (video_id, date),
    FOREIGN KEY (video_id) REFERENCES videos(video_id)
);

CREATE INDEX IF NOT EXISTS idx_metrics_daily_date ON metrics_daily(date);

CREATE TABLE IF NOT EXISTS retention_curve (
    video_id            TEXT NOT NULL,
    snapshot_date       TEXT NOT NULL,    -- YYYY-MM-DD when we pulled it
    elapsed_ratio       REAL NOT NULL,    -- 0.0..1.0 bucket midpoint
    relative_retention  REAL,             -- audienceWatchRatio
    PRIMARY KEY (video_id, snapshot_date, elapsed_ratio),
    FOREIGN KEY (video_id) REFERENCES videos(video_id)
);
"""


@contextmanager
def connect(db_path: Path):
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    try:
        conn.executescript(SCHEMA)
        # Idempotent ALTERs for columns added after the initial schema.
        existing = {r[1] for r in conn.execute(
            "PRAGMA table_info(videos)").fetchall()}
        for col, decl in (('lifetime_impressions', 'INTEGER'),
                          ('lifetime_ctr', 'REAL')):
            if col not in existing:
                conn.execute(f'ALTER TABLE videos ADD COLUMN {col} {decl}')
        yield conn
        conn.commit()
    finally:
        conn.close()


def upsert_video(conn: sqlite3.Connection, row: dict) -> None:
    """Insert or merge a videos row. NULLs in `row` do not overwrite existing
    values — useful so a backfill metadata refresh doesn't clobber render
    context written at upload time."""
    cur = conn.execute('SELECT * FROM videos WHERE video_id = ?',
                       (row['video_id'],))
    existing = cur.fetchone()
    if existing is None:
        cols = list(row.keys())
        placeholders = ','.join('?' for _ in cols)
        conn.execute(
            f"INSERT INTO videos ({','.join(cols)}) VALUES ({placeholders})",
            [row[c] for c in cols])
        return
    merged = dict(existing)
    for k, v in row.items():
        if v is not None:
            merged[k] = v
    cols = [c for c in merged.keys() if c != 'video_id']
    sets = ','.join(f'{c}=?' for c in cols)
    conn.execute(f"UPDATE videos SET {sets} WHERE video_id=?",
                 [merged[c] for c in cols] + [row['video_id']])


def upsert_metrics_daily(conn: sqlite3.Connection,
                         rows: Iterable[dict]) -> int:
    n = 0
    for r in rows:
        cols = list(r.keys())
        placeholders = ','.join('?' for _ in cols)
        updates = ','.join(f'{c}=excluded.{c}' for c in cols
                           if c not in ('video_id', 'date'))
        conn.execute(
            f"INSERT INTO metrics_daily ({','.join(cols)}) "
            f"VALUES ({placeholders}) "
            f"ON CONFLICT(video_id, date) DO UPDATE SET {updates}",
            [r[c] for c in cols])
        n += 1
    return n


def upsert_retention(conn: sqlite3.Connection, rows: Iterable[dict]) -> int:
    n = 0
    for r in rows:
        conn.execute(
            "INSERT INTO retention_curve "
            "(video_id, snapshot_date, elapsed_ratio, relative_retention) "
            "VALUES (?, ?, ?, ?) "
            "ON CONFLICT(video_id, snapshot_date, elapsed_ratio) "
            "DO UPDATE SET relative_retention=excluded.relative_retention",
            (r['video_id'], r['snapshot_date'],
             r['elapsed_ratio'], r['relative_retention']))
        n += 1
    return n


def list_videos(conn: sqlite3.Connection,
                channel: str | None = None) -> list[sqlite3.Row]:
    if channel:
        cur = conn.execute(
            'SELECT * FROM videos WHERE channel=? ORDER BY uploaded_at DESC',
            (channel,))
    else:
        cur = conn.execute(
            'SELECT * FROM videos ORDER BY uploaded_at DESC')
    return cur.fetchall()


def db_path_for(repo_root: Path) -> Path:
    return Path(repo_root) / 'cache' / 'analytics.db'
