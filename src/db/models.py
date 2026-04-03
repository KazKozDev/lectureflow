"""SQLite database schema and connection management."""

import sqlite3
from pathlib import Path

from src.utils.logger import get_logger

logger = get_logger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS videos (
    video_id TEXT PRIMARY KEY,
    url TEXT NOT NULL,
    title TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS analyses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id TEXT NOT NULL,
    mode TEXT NOT NULL DEFAULT 'detailed',
    provider TEXT,
    model_name TEXT,
    language TEXT,
    skip_llm INTEGER NOT NULL DEFAULT 0,
    segment_count INTEGER NOT NULL,
    markdown TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (video_id) REFERENCES videos(video_id)
);

CREATE TABLE IF NOT EXISTS segments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    analysis_id INTEGER NOT NULL,
    start_time REAL NOT NULL,
    end_time REAL NOT NULL,
    text TEXT NOT NULL,
    topic TEXT,
    improved_topic TEXT,
    improved_text TEXT,
    segment_order INTEGER NOT NULL,
    FOREIGN KEY (analysis_id) REFERENCES analyses(id)
);

CREATE INDEX IF NOT EXISTS idx_analyses_video ON analyses(video_id);
CREATE INDEX IF NOT EXISTS idx_segments_analysis ON segments(analysis_id);

CREATE VIRTUAL TABLE IF NOT EXISTS segments_fts USING fts5(
    text,
    topic,
    improved_text,
    improved_topic,
    content='segments',
    content_rowid='id'
);

CREATE TRIGGER IF NOT EXISTS segments_ai AFTER INSERT ON segments BEGIN
  INSERT INTO segments_fts(rowid, text, topic, improved_text, improved_topic)
  VALUES (new.id, new.text, new.topic, new.improved_text, new.improved_topic);
END;

CREATE TRIGGER IF NOT EXISTS segments_ad AFTER DELETE ON segments BEGIN
  INSERT INTO segments_fts(segments_fts, rowid, text, topic, improved_text, improved_topic)
  VALUES('delete', old.id, old.text, old.topic, old.improved_text, old.improved_topic);
END;

CREATE TRIGGER IF NOT EXISTS segments_au AFTER UPDATE ON segments BEGIN
  INSERT INTO segments_fts(segments_fts, rowid, text, topic, improved_text, improved_topic)
  VALUES('delete', old.id, old.text, old.topic, old.improved_text, old.improved_topic);
  INSERT INTO segments_fts(rowid, text, topic, improved_text, improved_topic)
  VALUES (new.id, new.text, new.topic, new.improved_text, new.improved_topic);
END;
"""

ANALYSES_REQUIRED_COLUMNS = {
    "mode": "TEXT NOT NULL DEFAULT 'detailed'",
    "provider": "TEXT",
    "model_name": "TEXT",
    "language": "TEXT",
    "skip_llm": "INTEGER NOT NULL DEFAULT 0",
}


def get_connection(db_path: str) -> sqlite3.Connection:
    """Create a database connection and ensure schema exists.

    Args:
        db_path: Path to SQLite database file.

    Returns:
        SQLite connection with row_factory set to Row.
    """
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(path), check_same_thread=False, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")

    conn.executescript(SCHEMA)
    _ensure_analyses_columns(conn)

    # Rebuild FTS index to catch any records added before FTS was enabled
    try:
        conn.execute("INSERT INTO segments_fts(segments_fts) VALUES('rebuild')")
    except sqlite3.Error as e:
        logger.warning("FTS rebuild failed (this is usually fine on empty dbs): %s", e)

    logger.debug("Database initialized at %s", db_path)
    return conn


def _ensure_analyses_columns(conn: sqlite3.Connection) -> None:
    """Backfill newly introduced analyses columns on existing databases."""
    existing = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(analyses)").fetchall()
    }
    for column, definition in ANALYSES_REQUIRED_COLUMNS.items():
        if column not in existing:
            conn.execute(f"ALTER TABLE analyses ADD COLUMN {column} {definition}")
