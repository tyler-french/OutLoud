import sqlite3
from datetime import datetime

from config import DB_PATH


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
            completed_at TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()


def create_article(title: str, source_type: str, source_path: str, txt_path: str) -> int:
    conn = get_connection()
    cursor = conn.execute(
        """INSERT INTO articles (title, source_type, source_path, txt_path)
           VALUES (?, ?, ?, ?)""",
        (title, source_type, source_path, txt_path)
    )
    article_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return article_id


def get_article(article_id: int) -> dict | None:
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM articles WHERE id = ?", (article_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_all_articles() -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM articles ORDER BY created_at DESC"
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_pending_articles() -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM articles WHERE status != 'completed' ORDER BY created_at DESC"
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_completed_articles() -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM articles WHERE status = 'completed' ORDER BY completed_at DESC"
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def update_article_mp3(article_id: int, mp3_path: str):
    conn = get_connection()
    conn.execute(
        "UPDATE articles SET mp3_path = ?, status = 'ready' WHERE id = ?",
        (mp3_path, article_id)
    )
    conn.commit()
    conn.close()


def update_article_notes(article_id: int, notes: str):
    conn = get_connection()
    conn.execute(
        "UPDATE articles SET notes = ? WHERE id = ?",
        (notes, article_id)
    )
    conn.commit()
    conn.close()


def mark_article_completed(article_id: int):
    conn = get_connection()
    conn.execute(
        "UPDATE articles SET status = 'completed', completed_at = ? WHERE id = ?",
        (datetime.now().isoformat(), article_id)
    )
    conn.commit()
    conn.close()


def delete_article(article_id: int):
    conn = get_connection()
    conn.execute("DELETE FROM articles WHERE id = ?", (article_id,))
    conn.commit()
    conn.close()


init_db()
