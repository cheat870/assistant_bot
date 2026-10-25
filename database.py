import sqlite3
from typing import List, Optional
from datetime import datetime
from config import DB_PATH

def init_db():
    """Initialize database tables."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Table for subscribers of holiday alerts
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS alert_subscribers (
            chat_id INTEGER PRIMARY KEY,
            username TEXT,
            chat_type TEXT,
            subscribed_at TEXT,
            is_active INTEGER DEFAULT 1
        )
    """)
    
    # Table for statistics/logs (optional)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS download_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER,
            url TEXT,
            title TEXT,
            downloaded_at TEXT
        )
    """)
    
    conn.commit()
    conn.close()

def add_subscriber(chat_id: int, username: Optional[str], chat_type: str) -> bool:
    """Add or re-activate a subscriber."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    now_str = datetime.utcnow().isoformat()
    
    cursor.execute("""
        INSERT INTO alert_subscribers (chat_id, username, chat_type, subscribed_at, is_active)
        VALUES (?, ?, ?, ?, 1)
        ON CONFLICT(chat_id) DO UPDATE SET is_active = 1, username = excluded.username
    """, (chat_id, username, chat_type, now_str))
    
    conn.commit()
    conn.close()
    return True

def remove_subscriber(chat_id: int) -> bool:
    """Deactivate a subscriber."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE alert_subscribers SET is_active = 0 WHERE chat_id = ?
    """, (chat_id,))
    conn.commit()
    conn.close()
    return True

def is_subscribed(chat_id: int) -> bool:
    """Check if a chat is subscribed."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT is_active FROM alert_subscribers WHERE chat_id = ?
    """, (chat_id,))
    row = cursor.fetchone()
    conn.close()
    return bool(row and row[0] == 1)

def get_active_subscribers() -> List[int]:
    """Retrieve all active subscriber chat IDs."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT chat_id FROM alert_subscribers WHERE is_active = 1
    """)
    rows = cursor.fetchall()
    conn.close()
    return [row[0] for row in rows]

def log_download(chat_id: int, url: str, title: str):
    """Log video download for auditing."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO download_logs (chat_id, url, title, downloaded_at)
        VALUES (?, ?, ?, ?)
    """, (chat_id, url, title, datetime.utcnow().isoformat()))
    conn.commit()
    conn.close()
