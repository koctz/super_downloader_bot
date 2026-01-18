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
