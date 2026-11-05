import sqlite3
from typing import List, Optional, Dict, Any
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

    # Table for subscribers of 5:00 AM daily weather alerts and their location
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS weather_settings (
            chat_id INTEGER PRIMARY KEY,
            latitude REAL DEFAULT 11.5564,
            longitude REAL DEFAULT 104.9282,
            location_name TEXT DEFAULT 'រាជធានីភ្នំពេញ',
            is_active INTEGER DEFAULT 1,
            updated_at TEXT
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

    # Table for personal custom reminders
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER,
            remind_at TEXT,
            remind_time_str TEXT,
            message TEXT,
            is_triggered INTEGER DEFAULT 0,
            created_at TEXT
        )
    """)

    # Table for continuous AI chat mode
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ai_sessions (
            chat_id INTEGER PRIMARY KEY,
            is_continuous INTEGER DEFAULT 0,
            updated_at TEXT
        )
    """)

    # Table for AI conversation context memory
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ai_chat_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER,
            role TEXT,
            content TEXT,
            created_at TEXT
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

# -------------------------------------------------------------
# Weather Settings Operations
# -------------------------------------------------------------
def get_user_weather_settings(chat_id: int) -> Dict[str, Any]:
    """Retrieve weather settings for a user. Defaults to Phnom Penh."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT latitude, longitude, location_name, is_active
        FROM weather_settings WHERE chat_id = ?
    """, (chat_id,))
    row = cursor.fetchone()
    conn.close()
    
    if row:
        return {
            "chat_id": chat_id,
            "latitude": row[0],
            "longitude": row[1],
            "location_name": row[2] or "រាជធានីភ្នំពេញ",
            "is_active": bool(row[3])
        }
    return {
        "chat_id": chat_id,
        "latitude": 11.5564,
        "longitude": 104.9282,
        "location_name": "រាជធានីភ្នំពេញ",
        "is_active": True
    }

def set_user_location(chat_id: int, lat: float, lon: float, location_name: str) -> bool:
    """Save or update user's GPS coordinates and location name."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    now_str = datetime.utcnow().isoformat()
    
    cursor.execute("""
        INSERT INTO weather_settings (chat_id, latitude, longitude, location_name, is_active, updated_at)
        VALUES (?, ?, ?, ?, 1, ?)
        ON CONFLICT(chat_id) DO UPDATE SET
            latitude = excluded.latitude,
            longitude = excluded.longitude,
            location_name = excluded.location_name,
            updated_at = excluded.updated_at
    """, (chat_id, lat, lon, location_name, now_str))
    
    conn.commit()
    conn.close()
    return True

def set_weather_alert_active(chat_id: int, is_active: bool) -> bool:
    """Enable or disable 5:00 AM weather alerts for a user."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    now_str = datetime.utcnow().isoformat()
    val = 1 if is_active else 0
    
    cursor.execute("""
        INSERT INTO weather_settings (chat_id, is_active, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(chat_id) DO UPDATE SET
            is_active = excluded.is_active,
            updated_at = excluded.updated_at
    """, (chat_id, val, now_str))
    
    conn.commit()
    conn.close()
    return True

def get_active_weather_subscribers() -> List[Dict[str, Any]]:
    """Get all users subscribed to the 5:00 AM daily weather alert."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT chat_id, latitude, longitude, location_name
        FROM weather_settings WHERE is_active = 1
    """)
    rows = cursor.fetchall()
    conn.close()
    
    results = []
    for r in rows:
        results.append({
            "chat_id": r[0],
            "latitude": r[1] if r[1] is not None else 11.5564,
            "longitude": r[2] if r[2] is not None else 104.9282,
            "location_name": r[3] or "រាជធានីភ្នំពេញ"
        })
    return results

# -------------------------------------------------------------
# Personal Reminders Operations
# -------------------------------------------------------------
def add_reminder(chat_id: int, remind_at: str, remind_time_str: str, message: str) -> int:
    """Create a new custom reminder."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO reminders (chat_id, remind_at, remind_time_str, message, is_triggered, created_at)
        VALUES (?, ?, ?, ?, 0, ?)
    """, (chat_id, remind_at, remind_time_str, message, datetime.utcnow().isoformat()))
    rem_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return rem_id

def get_due_reminders(now_iso: str) -> List[Dict[str, Any]]:
    """Get all reminders whose time has passed and not yet triggered."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, chat_id, remind_time_str, message
        FROM reminders
        WHERE remind_at <= ? AND is_triggered = 0
    """, (now_iso,))
    rows = cursor.fetchall()
    conn.close()
    return [{"id": r[0], "chat_id": r[1], "time_str": r[2], "message": r[3]} for r in rows]

def mark_reminder_done(reminder_id: int):
    """Mark a reminder as triggered."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE reminders SET is_triggered = 1 WHERE id = ?", (reminder_id,))
    conn.commit()
    conn.close()

def get_user_reminders(chat_id: int) -> List[Dict[str, Any]]:
    """Get list of active reminders for a user."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, remind_time_str, message
        FROM reminders
        WHERE chat_id = ? AND is_triggered = 0
        ORDER BY remind_at ASC
    """, (chat_id,))
    rows = cursor.fetchall()
    conn.close()
    return [{"id": r[0], "time_str": r[1], "message": r[2]} for r in rows]

def delete_reminder(reminder_id: int, chat_id: int) -> bool:
    """Delete a reminder by ID."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM reminders WHERE id = ? AND chat_id = ?", (reminder_id, chat_id))
    affected = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return affected

# -------------------------------------------------------------
# Continuous AI Mode & Conversation Memory Operations
# -------------------------------------------------------------
def is_ai_mode(chat_id: int) -> bool:
    """Check if a chat has continuous AI chat mode enabled."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT is_continuous FROM ai_sessions WHERE chat_id = ?", (chat_id,))
    row = cursor.fetchone()
    conn.close()
    return bool(row and row[0] == 1)

def set_ai_mode(chat_id: int, enabled: bool) -> bool:
    """Toggle continuous AI chat mode for a chat."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    now_str = datetime.utcnow().isoformat()
    val = 1 if enabled else 0
    cursor.execute("""
        INSERT INTO ai_sessions (chat_id, is_continuous, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(chat_id) DO UPDATE SET is_continuous = excluded.is_continuous, updated_at = excluded.updated_at
    """, (chat_id, val, now_str))
    conn.commit()
    conn.close()
    return True

def save_chat_message(chat_id: int, role: str, content: str):
    """Save an AI message to conversation memory."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO ai_chat_history (chat_id, role, content, created_at)
        VALUES (?, ?, ?, ?)
    """, (chat_id, role, content, datetime.utcnow().isoformat()))
    conn.commit()
    conn.close()

def get_chat_history(chat_id: int, limit: int = 8) -> List[Dict[str, str]]:
    """Retrieve recent chat history for context memory."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT role, content FROM (
            SELECT id, role, content FROM ai_chat_history
            WHERE chat_id = ?
            ORDER BY id DESC LIMIT ?
        ) ORDER BY id ASC
    """, (chat_id, limit))
    rows = cursor.fetchall()
    conn.close()
    return [{"role": r[0], "content": r[1]} for r in rows]

def clear_chat_history(chat_id: int):
    """Clear AI conversation memory for a chat."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM ai_chat_history WHERE chat_id = ?", (chat_id,))
    conn.commit()
    conn.close()

def get_all_registered_chats() -> List[int]:
    """Get all unique chat IDs across subscribers, reminders and settings for admin broadcast."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT DISTINCT chat_id FROM (
            SELECT chat_id FROM alert_subscribers
            UNION
            SELECT chat_id FROM weather_settings
            UNION
            SELECT chat_id FROM ai_sessions
        )
    """)
    rows = cursor.fetchall()
    conn.close()
    return [r[0] for r in rows]
