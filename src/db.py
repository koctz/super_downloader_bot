import sqlite3
from pathlib import Path
from datetime import datetime

DB_PATH = Path("data/bot.db")  # можешь поменять путь, если нужно
DB_PATH.parent.mkdir(parents=True, exist_ok=True)


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            username TEXT,
            full_name TEXT,
            lang TEXT,
            registered_at TEXT,
            last_active TEXT,
            downloads INTEGER DEFAULT 0,
            blocked INTEGER DEFAULT 0
        )
        """
    )

    conn.commit()
    conn.close()
    def add_or_update_user(user_id: int, username: str | None, full_name: str | None, lang: str | None = "ru"):
    now = datetime.utcnow().isoformat()
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        INSERT INTO users (id, username, full_name, lang, registered_at, last_active)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            username=excluded.username,
            full_name=excluded.full_name,
            lang=COALESCE(excluded.lang, lang),
            last_active=excluded.last_active
        """,
        (user_id, username, full_name, lang, now, now),
    )

    conn.commit()
    conn.close()


def update_last_active(user_id: int):
    now = datetime.utcnow().isoformat()
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("UPDATE users SET last_active=? WHERE id=?", (now, user_id))
    conn.commit()
    conn.close()


def increment_downloads(user_id: int):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("UPDATE users SET downloads = downloads + 1 WHERE id=?", (user_id,))
    conn.commit()
    conn.close()


def get_users_page(page: int, per_page: int = 20):
    offset = page * per_page
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, username, full_name, lang, registered_at, last_active, downloads, blocked FROM users "
        "ORDER BY registered_at DESC LIMIT ? OFFSET ?",
        (per_page, offset),
    )
    rows = cur.fetchall()
    conn.close()
    return rows


def get_users_count():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) AS c FROM users")
    row = cur.fetchone()
    conn.close()
    return row["c"] if row else 0

