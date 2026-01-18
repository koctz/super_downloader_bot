import sqlite3
import threading

DB_PATH = "data/users.db"

_lock = threading.Lock()

def init_db():
    with _lock:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                username TEXT,
                full_name TEXT,
                lang TEXT,
                downloads INTEGER DEFAULT 0,
                last_active INTEGER DEFAULT 0
            )
        """)

        conn.commit()
        conn.close()

def add_user(user_id, username, full_name, lang):
    with _lock:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT OR IGNORE INTO users (id, username, full_name, lang)
            VALUES (?, ?, ?, ?)
        """, (user_id, username, full_name, lang))

        conn.commit()
        conn.close()

def update_last_active(user_id, timestamp):
    with _lock:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        cursor.execute("""
            UPDATE users SET last_active = ? WHERE id = ?
        """, (timestamp, user_id))

        conn.commit()
        conn.close()

def increment_downloads(user_id):
    with _lock:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        cursor.execute("""
            UPDATE users SET downloads = downloads + 1 WHERE id = ?
        """, (user_id,))

        conn.commit()
        conn.close()
def get_users(offset=0, limit=20):
    with _lock:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT id, username, full_name, lang, downloads, last_active
            FROM users
            ORDER BY id ASC
            LIMIT ? OFFSET ?
        """, (limit, offset))

        rows = cursor.fetchall()
        conn.close()
        return rows


def count_users():
    with _lock:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM users")
        total = cursor.fetchone()[0]

        conn.close()
        return total


def get_all_user_ids():
    with _lock:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        cursor.execute("SELECT id FROM users")
        rows = cursor.fetchall()

        conn.close()
        return [row[0] for row in rows]
