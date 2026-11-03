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
