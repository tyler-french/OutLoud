import sqlite3
from datetime import datetime

from outloud.config import DB_PATH


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS articles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            source_type TEXT NOT NULL,
            source_path TEXT NOT NULL,
            txt_path TEXT,
            mp3_path TEXT,
            notes TEXT DEFAULT '',
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMP,
            raw_txt_path TEXT,
            cleaned_txt_path TEXT,
            voice TEXT DEFAULT 'am_adam',
            processing_stage TEXT DEFAULT 'queued',
            error TEXT,
            content_hash TEXT,
            progress TEXT,
            was_cleaned INTEGER DEFAULT 0
        )
    """)
    conn.commit()
    _migrate_db(conn)
    conn.close()


def _migrate_db(conn):
    """Add new columns to existing databases."""
    cursor = conn.execute("PRAGMA table_info(articles)")
    columns = {row[1] for row in cursor.fetchall()}

    migrations = [
        ("raw_txt_path", "TEXT"),
        ("cleaned_txt_path", "TEXT"),
        ("voice", "TEXT DEFAULT 'am_adam'"),
        ("processing_stage", "TEXT DEFAULT 'queued'"),
        ("error", "TEXT"),
        ("content_hash", "TEXT"),
        ("progress", "TEXT"),
        ("was_cleaned", "INTEGER DEFAULT 0"),
        ("timestamps_path", "TEXT"),
    ]

    for col_name, col_type in migrations:
        if col_name not in columns:
            if not col_name.isidentifier():
                raise ValueError(f"Invalid column name: {col_name}")
            if not all(c.isalnum() or c in " '_()" for c in col_type):
                raise ValueError(f"Invalid column type: {col_type}")
            conn.execute(f"ALTER TABLE articles ADD COLUMN {col_name} {col_type}")

    conn.execute("""
        UPDATE articles
        SET processing_stage = 'ready',
            raw_txt_path = txt_path,
            cleaned_txt_path = txt_path
        WHERE status = 'ready'
          AND processing_stage IS NULL
          AND txt_path IS NOT NULL
    """)

    conn.execute("""
        UPDATE articles
        SET processing_stage = 'completed'
        WHERE status = 'completed'
          AND processing_stage IS NULL
    """)

    conn.execute("""
        UPDATE articles
        SET processing_stage = 'queued'
        WHERE processing_stage IN ('extracting', 'cleaning', 'generating')
    """)

    conn.commit()


def create_article(
    title: str,
    source_type: str,
    source_path: str,
    txt_path: str | None = None,
    voice: str = "am_adam",
    content_hash: str | None = None,
) -> int:
    conn = get_connection()
    cursor = conn.execute(
        """INSERT INTO articles (title, source_type, source_path, txt_path, voice, processing_stage, content_hash)
           VALUES (?, ?, ?, ?, ?, 'queued', ?)""",
        (title, source_type, source_path, txt_path, voice, content_hash),
    )
    article_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return article_id


def get_article_by_hash(content_hash: str) -> dict | None:
    """Find an article by its content hash."""
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM articles WHERE content_hash = ?", (content_hash,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_article(article_id: int) -> dict | None:
    conn = get_connection()
    row = conn.execute("SELECT * FROM articles WHERE id = ?", (article_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_all_articles() -> list[dict]:
    conn = get_connection()
    rows = conn.execute("SELECT * FROM articles ORDER BY created_at DESC").fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_pending_articles() -> list[dict]:
    """Get articles that are not completed (for display)."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM articles WHERE status != 'completed' ORDER BY created_at DESC"
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_articles_to_process() -> list[dict]:
    """Get articles that need processing (not in terminal state)."""
    conn = get_connection()
    rows = conn.execute(
        """SELECT * FROM articles
           WHERE processing_stage NOT IN ('ready', 'completed', 'error')
           ORDER BY created_at ASC"""
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


_ARTICLE_COLUMNS = frozenset(
    [
        "title",
        "source_type",
        "source_path",
        "txt_path",
        "mp3_path",
        "notes",
        "status",
        "raw_txt_path",
        "cleaned_txt_path",
        "voice",
        "processing_stage",
        "error",
        "content_hash",
        "progress",
        "was_cleaned",
        "timestamps_path",
    ]
)

_VALID_STAGES = frozenset(
    [
        "queued",
        "extracting",
        "extracted",
        "cleaning",
        "cleaned",
        "generating",
        "ready",
        "error",
    ]
)


def update_article_stage(article_id: int, stage: str, **kwargs):
    """Update processing stage and optionally other fields."""
    if stage not in _VALID_STAGES:
        raise ValueError(f"Invalid processing stage: {stage}")

    conn = get_connection()
    sets = ["processing_stage = ?"]
    values = [stage]

    for key, value in kwargs.items():
        if key not in _ARTICLE_COLUMNS:
            raise ValueError(f"Invalid column name: {key}")
        sets.append(f"{key} = ?")
        values.append(value)

    values.append(article_id)
    conn.execute(
        f"UPDATE articles SET {', '.join(sets)} WHERE id = ?",
        values,
    )
    conn.commit()
    conn.close()


def set_article_error(article_id: int, error_message: str):
    """Mark article as failed with error message."""
    conn = get_connection()
    conn.execute(
        "UPDATE articles SET processing_stage = 'error', error = ? WHERE id = ?",
        (error_message, article_id),
    )
    conn.commit()
    conn.close()


def reset_article_for_reprocessing(article_id: int):
    """Reset article to be reprocessed from the beginning."""
    conn = get_connection()
    conn.execute(
        """UPDATE articles
           SET processing_stage = 'queued', error = NULL, progress = NULL
           WHERE id = ?""",
        (article_id,),
    )
    conn.commit()
    conn.close()


def reset_article_for_cleaning(article_id: int):
    """Reset article to run cleaning stage."""
    conn = get_connection()
    conn.execute(
        """UPDATE articles
           SET processing_stage = 'extracted',
               cleaned_txt_path = NULL,
               mp3_path = NULL,
               error = NULL,
               progress = NULL,
               was_cleaned = 0
           WHERE id = ?""",
        (article_id,),
    )
    conn.commit()
    conn.close()


def reset_article_for_audio(article_id: int, voice: str):
    """Reset article to regenerate audio with a different voice."""
    conn = get_connection()
    conn.execute(
        """UPDATE articles
           SET processing_stage = 'cleaned',
               mp3_path = NULL,
               voice = ?,
               error = NULL,
               progress = NULL
           WHERE id = ?""",
        (voice, article_id),
    )
    conn.commit()
    conn.close()


def update_article_progress(article_id: int, progress: str):
    """Update the progress text for an article."""
    if not all(c.isalnum() or c in " /()-" for c in progress):
        raise ValueError(f"Invalid progress text: {progress}")
    conn = get_connection()
    conn.execute(
        "UPDATE articles SET progress = ? WHERE id = ?",
        (progress, article_id),
    )
    conn.commit()
    conn.close()


def get_completed_articles() -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM articles WHERE status = 'completed' ORDER BY completed_at DESC"
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def update_article_mp3(
    article_id: int, mp3_path: str, timestamps_path: str | None = None
):
    conn = get_connection()
    if timestamps_path:
        conn.execute(
            """UPDATE articles
               SET mp3_path = ?, timestamps_path = ?, status = 'ready', processing_stage = 'ready'
               WHERE id = ?""",
            (mp3_path, timestamps_path, article_id),
        )
    else:
        conn.execute(
            """UPDATE articles
               SET mp3_path = ?, status = 'ready', processing_stage = 'ready'
               WHERE id = ?""",
            (mp3_path, article_id),
        )
    conn.commit()
    conn.close()


def update_article_notes(article_id: int, notes: str):
    conn = get_connection()
    conn.execute("UPDATE articles SET notes = ? WHERE id = ?", (notes, article_id))
    conn.commit()
    conn.close()


def mark_article_completed(article_id: int):
    conn = get_connection()
    conn.execute(
        """UPDATE articles
           SET status = 'completed', processing_stage = 'completed', completed_at = ?
           WHERE id = ?""",
        (datetime.now().isoformat(), article_id),
    )
    conn.commit()
    conn.close()


def delete_article(article_id: int):
    conn = get_connection()
    conn.execute("DELETE FROM articles WHERE id = ?", (article_id,))
    conn.commit()
    conn.close()


init_db()
