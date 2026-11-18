import os
import sqlite3
import logging
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime, timedelta
from config import DB_PATH

logger = logging.getLogger(__name__)

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

    # Table for Personal Expense & Income Tracker
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER,
            type TEXT, -- 'expense' or 'income'
            amount REAL,
            currency TEXT, -- 'USD' or 'KHR'
            category TEXT,
            note TEXT,
            created_at TEXT
        )
    """)

    # Table for Group Settings (Anti-Spam & Moderation & Welcome)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS group_settings (
            chat_id INTEGER PRIMARY KEY,
            antispam_enabled INTEGER DEFAULT 1,
            welcome_enabled INTEGER DEFAULT 1,
            updated_at TEXT
        )
    """)

    # Table for Chat with PDF Sessions
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS pdf_sessions (
            chat_id INTEGER PRIMARY KEY,
            filename TEXT,
            summary TEXT,
            extracted_text TEXT,
            total_pages INTEGER DEFAULT 1,
            updated_at TEXT
        )
    """)

    # Table for Auto-Clean Message Tracking (20-Minute Auto-Delete)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS auto_clean_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER,
            message_id INTEGER,
            created_at TEXT
        )
    """)

    # Table for Auto-Clean Settings (defaults to enabled=1, interval=20m)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS auto_clean_settings (
            chat_id INTEGER PRIMARY KEY,
            is_enabled INTEGER DEFAULT 1,
            clean_interval_minutes INTEGER DEFAULT 20,
            updated_at TEXT
        )
    """)

    # Table for Long-Term Vector / Semantic Memory
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_long_term_memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            category TEXT NOT NULL,
            memory_key TEXT NOT NULL,
            content TEXT NOT NULL,
            embedding TEXT,
            created_at TEXT,
            updated_at TEXT,
            UNIQUE(chat_id, memory_key)
        )
    """)

    # Table for Crypto & TON Price Alerts
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS crypto_price_alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            symbol TEXT NOT NULL,
            target_price REAL NOT NULL,
            condition TEXT NOT NULL,
            created_price REAL NOT NULL,
            is_triggered INTEGER DEFAULT 0,
            created_at TEXT
        )
    """)

    # Table for Dynamic Bot Global Settings (Key-Value Store)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bot_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)

    # Table for Media URL Tokens (persistent cache for callback buttons)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS media_tokens (
            token TEXT PRIMARY KEY,
            url TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    # Table for Music Channel Archive Logs
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS music_archive (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER,
            query TEXT,
            title TEXT,
            performer TEXT,
            duration INTEGER,
            file_id TEXT,
            channel_id TEXT,
            channel_message_id INTEGER,
            archived_at TEXT
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
        lat = row[0] if (row[0] is not None and isinstance(row[0], (int, float))) else 11.5564
        lon = row[1] if (row[1] is not None and isinstance(row[1], (int, float))) else 104.9282
        return {
            "chat_id": chat_id,
            "latitude": lat,
            "longitude": lon,
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
    """Get all unique chat IDs across subscribers, reminders, settings and auto-clean."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT DISTINCT chat_id FROM (
            SELECT chat_id FROM alert_subscribers
            UNION
            SELECT chat_id FROM weather_settings
            UNION
            SELECT chat_id FROM ai_sessions
            UNION
            SELECT chat_id FROM expenses
            UNION
            SELECT chat_id FROM auto_clean_settings
            UNION
            SELECT chat_id FROM auto_clean_messages
        )
    """)
    rows = cursor.fetchall()
    conn.close()
    return [r[0] for r in rows]

# -------------------------------------------------------------
# Personal Expense & Income Tracker Operations
# -------------------------------------------------------------
def add_transaction(chat_id: int, tx_type: str, amount: float, currency: str, category: str, note: str) -> int:
    """Record an income or expense transaction."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    now_str = datetime.utcnow().isoformat()
    cursor.execute("""
        INSERT INTO expenses (chat_id, type, amount, currency, category, note, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (chat_id, tx_type, amount, currency.upper(), category, note, now_str))
    tx_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return tx_id

def get_expense_summary(chat_id: int, days: int = 30) -> Dict[str, Any]:
    """Calculate expense & income totals and category breakdown over past N days."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    since_date = (datetime.utcnow() - timedelta(days=days)).isoformat()
    
    # Total expense & income by currency
    cursor.execute("""
        SELECT type, currency, SUM(amount)
        FROM expenses
        WHERE chat_id = ? AND created_at >= ?
        GROUP BY type, currency
    """, (chat_id, since_date))
    rows = cursor.fetchall()
    
    summary = {
        "expense_usd": 0.0,
        "expense_khr": 0.0,
        "income_usd": 0.0,
        "income_khr": 0.0,
        "categories_usd": {},
        "categories_khr": {}
    }
    
    for tx_type, curr, total in rows:
        val = float(total or 0.0)
        curr_upper = (curr or "USD").upper()
        if tx_type == "expense":
            if curr_upper == "KHR":
                summary["expense_khr"] = val
            else:
                summary["expense_usd"] = val
        elif tx_type == "income":
            if curr_upper == "KHR":
                summary["income_khr"] = val
            else:
                summary["income_usd"] = val

    # Category breakdown for expenses
    cursor.execute("""
        SELECT category, currency, SUM(amount)
        FROM expenses
        WHERE chat_id = ? AND type = 'expense' AND created_at >= ?
        GROUP BY category, currency
        ORDER BY SUM(amount) DESC
    """, (chat_id, since_date))
    cat_rows = cursor.fetchall()
    for cat, curr, total in cat_rows:
        curr_upper = (curr or "USD").upper()
        val = float(total or 0.0)
        if curr_upper == "KHR":
            summary["categories_khr"][cat] = val
        else:
            summary["categories_usd"][cat] = val

    conn.close()
    return summary

def get_recent_transactions(chat_id: int, limit: int = 10) -> List[Dict[str, Any]]:
    """Retrieve recent transaction history for a user."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, type, amount, currency, category, note, created_at
        FROM expenses
        WHERE chat_id = ?
        ORDER BY id DESC LIMIT ?
    """, (chat_id, limit))
    rows = cursor.fetchall()
    conn.close()
    return [
        {
            "id": r[0],
            "type": r[1],
            "amount": r[2],
            "currency": r[3],
            "category": r[4],
            "note": r[5],
            "created_at": r[6]
        }
        for r in rows
    ]

def delete_transaction(tx_id: int, chat_id: int) -> bool:
    """Delete a transaction by ID."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM expenses WHERE id = ? AND chat_id = ?", (tx_id, chat_id))
    affected = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return affected

def clear_user_expenses(chat_id: int) -> int:
    """Clear all expenses and income history for a chat."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM expenses WHERE chat_id = ?", (chat_id,))
    deleted = cursor.rowcount
    conn.commit()
    conn.close()
    return deleted

# -------------------------------------------------------------
# Group Settings & Anti-Spam Operations
# -------------------------------------------------------------
def is_antispam_enabled(chat_id: int) -> bool:
    """Check if anti-spam is enabled for a group."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT antispam_enabled FROM group_settings WHERE chat_id = ?", (chat_id,))
    row = cursor.fetchone()
    conn.close()
    if row is not None:
        return bool(row[0])
    return True  # Enabled by default

def set_antispam_enabled(chat_id: int, enabled: bool) -> bool:
    """Enable or disable anti-spam for a group."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    now_str = datetime.utcnow().isoformat()
    val = 1 if enabled else 0
    cursor.execute("""
        INSERT INTO group_settings (chat_id, antispam_enabled, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(chat_id) DO UPDATE SET
            antispam_enabled = excluded.antispam_enabled,
            updated_at = excluded.updated_at
    """, (chat_id, val, now_str))
    conn.commit()
    conn.close()
    return True

def is_welcome_enabled(chat_id: int) -> bool:
    """Check if welcome banner is enabled for a group."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT welcome_enabled FROM group_settings WHERE chat_id = ?", (chat_id,))
    row = cursor.fetchone()
    conn.close()
    if row is not None and row[0] is not None:
        return bool(row[0])
    return True  # Enabled by default

def set_welcome_enabled(chat_id: int, enabled: bool) -> bool:
    """Enable or disable welcome banner for a group."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    now_str = datetime.utcnow().isoformat()
    val = 1 if enabled else 0
    cursor.execute("""
        INSERT INTO group_settings (chat_id, welcome_enabled, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(chat_id) DO UPDATE SET
            welcome_enabled = excluded.welcome_enabled,
            updated_at = excluded.updated_at
    """, (chat_id, val, now_str))
    conn.commit()
    conn.close()
    return True

# -------------------------------------------------------------
# Chat with PDF Sessions Operations
# -------------------------------------------------------------
def save_pdf_session(chat_id: int, filename: str, summary: str, extracted_text: str, total_pages: int = 1) -> bool:
    """Save or update an active PDF session for follow-up Q&A."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    now_str = datetime.utcnow().isoformat()
    cursor.execute("""
        INSERT INTO pdf_sessions (chat_id, filename, summary, extracted_text, total_pages, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(chat_id) DO UPDATE SET
            filename = excluded.filename,
            summary = excluded.summary,
            extracted_text = excluded.extracted_text,
            total_pages = excluded.total_pages,
            updated_at = excluded.updated_at
    """, (chat_id, filename, summary, extracted_text, total_pages, now_str))
    conn.commit()
    conn.close()
    return True

def get_pdf_session(chat_id: int) -> Optional[Dict[str, Any]]:
    """Retrieve active PDF session for a chat."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT filename, summary, extracted_text, total_pages, updated_at
        FROM pdf_sessions WHERE chat_id = ?
    """, (chat_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    return {
        "filename": row[0],
        "summary": row[1],
        "extracted_text": row[2],
        "total_pages": row[3],
        "updated_at": row[4]
    }

def clear_pdf_session(chat_id: int) -> bool:
    """Remove active PDF session."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM pdf_sessions WHERE chat_id = ?", (chat_id,))
    conn.commit()
    conn.close()
    return True

# -------------------------------------------------------------
# Scheduled Twice-Daily Auto-Clean & History Management Operations
# -------------------------------------------------------------
def record_auto_clean_message(chat_id: int, message_id: int):
    """Record a message for the twice-daily auto-clean cycle (3AM & 12PM)."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO auto_clean_messages (chat_id, message_id, created_at)
        VALUES (?, ?, ?)
    """, (chat_id, message_id, datetime.utcnow().isoformat()))
    conn.commit()
    conn.close()

def get_expired_auto_clean_messages(cutoff_iso: str) -> List[Tuple[int, int, int]]:
    """Retrieve all messages that are older than cutoff timestamp (rec_id, chat_id, message_id)."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT m.id, m.chat_id, m.message_id
        FROM auto_clean_messages m
        LEFT JOIN auto_clean_settings s ON m.chat_id = s.chat_id
        WHERE m.created_at <= ? AND (s.is_enabled IS NULL OR s.is_enabled = 1)
        ORDER BY m.created_at ASC
        LIMIT 200
    """, (cutoff_iso,))
    rows = cursor.fetchall()
    conn.close()
    return rows

def delete_auto_clean_message_records(record_ids: List[int]):
    """Remove deleted message records from database."""
    if not record_ids:
        return
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    placeholders = ",".join(["?"] * len(record_ids))
    cursor.execute(f"DELETE FROM auto_clean_messages WHERE id IN ({placeholders})", record_ids)
    conn.commit()
    conn.close()

def is_auto_clean_enabled(chat_id: int) -> bool:
    """Check if scheduled auto-clean (3AM & 12PM) is enabled for this chat (defaults to True)."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT is_enabled FROM auto_clean_settings WHERE chat_id = ?", (chat_id,))
    row = cursor.fetchone()
    conn.close()
    return bool(row[0] == 1) if row else True

def set_auto_clean_enabled(chat_id: int, enabled: bool):
    """Enable or disable scheduled auto-clean for this chat."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO auto_clean_settings (chat_id, is_enabled, clean_interval_minutes, updated_at)
        VALUES (?, ?, 0, ?)
        ON CONFLICT(chat_id) DO UPDATE SET
            is_enabled = excluded.is_enabled,
            updated_at = excluded.updated_at
    """, (chat_id, 1 if enabled else 0, datetime.utcnow().isoformat()))
    conn.commit()
    conn.close()

def get_all_auto_clean_chats() -> List[int]:
    """Retrieve all chat IDs that have scheduled auto-clean enabled."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    all_chats = get_all_registered_chats()
    cursor.execute("SELECT chat_id FROM auto_clean_settings WHERE is_enabled = 0")
    disabled_chats = set(r[0] for r in cursor.fetchall())
    conn.close()
    return [c for c in all_chats if c not in disabled_chats]

def get_auto_clean_messages_for_chat(chat_id: int) -> List[Tuple[int, int]]:
    """Retrieve all recorded messages for a specific chat (id, message_id)."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, message_id FROM auto_clean_messages WHERE chat_id = ? ORDER BY id ASC
    """, (chat_id,))
    rows = cursor.fetchall()
    conn.close()
    return rows

def clear_auto_clean_messages_for_chat(chat_id: int):
    """Remove all message tracking records for a specific chat."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM auto_clean_messages WHERE chat_id = ?", (chat_id,))
    conn.commit()
    conn.close()

# -------------------------------------------------------------
# Long-Term Semantic & Vector Memory Operations
# -------------------------------------------------------------
def save_user_memory(chat_id: int, category: str, memory_key: str, content: str, embedding: Optional[str] = None):
    """Save or update a persistent user memory item (e.g. music preference, habit, birthday)."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    now_iso = datetime.utcnow().isoformat()
    cursor.execute("""
        INSERT INTO user_long_term_memories (chat_id, category, memory_key, content, embedding, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(chat_id, memory_key) DO UPDATE SET
            category = excluded.category,
            content = excluded.content,
            embedding = coalesce(excluded.embedding, user_long_term_memories.embedding),
            updated_at = excluded.updated_at
    """, (chat_id, category, memory_key, content, embedding, now_iso, now_iso))
    conn.commit()
    conn.close()

def get_user_memories(chat_id: int, category: Optional[str] = None) -> List[Dict[str, Any]]:
    """Retrieve stored long-term memories for a user, optionally filtered by category."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    if category:
        cursor.execute("""
            SELECT id, category, memory_key, content, embedding, updated_at
            FROM user_long_term_memories
            WHERE chat_id = ? AND category = ?
            ORDER BY updated_at DESC
        """, (chat_id, category))
    else:
        cursor.execute("""
            SELECT id, category, memory_key, content, embedding, updated_at
            FROM user_long_term_memories
            WHERE chat_id = ?
            ORDER BY updated_at DESC
        """, (chat_id,))
    rows = cursor.fetchall()
    conn.close()
    return [
        {
            "id": r[0],
            "category": r[1],
            "key": r[2],
            "content": r[3],
            "embedding": r[4],
            "updated_at": r[5],
        }
        for r in rows
    ]

def delete_user_memory(chat_id: int, memory_id: int) -> bool:
    """Delete a single memory item by id."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM user_long_term_memories WHERE chat_id = ? AND id = ?", (chat_id, memory_id))
    affected = cursor.rowcount
    conn.commit()
    conn.close()
    return affected > 0

def clear_user_memories(chat_id: int) -> int:
    """Clear all long-term memories for a user."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM user_long_term_memories WHERE chat_id = ?", (chat_id,))
    deleted = cursor.rowcount
    conn.commit()
    conn.close()
    return deleted

# -------------------------------------------------------------
# Enterprise PostgreSQL / Supabase Connector & Compatibility Helper
# -------------------------------------------------------------
def get_database_info() -> Dict[str, Any]:
    """Return database engine status (PostgreSQL ready or local SQLite)."""
    db_url = os.getenv("DATABASE_URL", "")
    is_postgres = bool(db_url and ("postgres://" in db_url or "postgresql://" in db_url))
    return {
        "engine": "PostgreSQL (Enterprise/Supabase)" if is_postgres else "SQLite3 (Local / Fast Embedded)",
        "is_postgres": is_postgres,
        "database_url_configured": bool(db_url),
        "sqlite_path": str(DB_PATH),
    }

def find_users_in_db(query: str) -> List[Dict[str, Any]]:
    """Search registered users/chats in local database by username or chat_id."""
    clean_q = query.lstrip("@").strip().lower()
    if not clean_q:
        return []
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT chat_id, username, chat_type, subscribed_at
            FROM alert_subscribers
            WHERE LOWER(username) = ? OR CAST(chat_id AS TEXT) = ?
            LIMIT 10
        """, (clean_q, clean_q))
        rows = cursor.fetchall()
        conn.close()
        return [
            {
                "chat_id": r[0],
                "username": r[1],
                "chat_type": r[2],
                "subscribed_at": r[3]
            }
            for r in rows
        ]
    except Exception as e:
        logger.warning(f"Error querying alert_subscribers: {e}")
        return []

# -------------------------------------------------------------
# Crypto & TON Price Alerts Database Operations
# -------------------------------------------------------------
def add_crypto_alert(chat_id: int, symbol: str, target_price: float, condition: str, created_price: float) -> int:
    """Create a new crypto price threshold alert."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO crypto_price_alerts (chat_id, symbol, target_price, condition, created_price, is_triggered, created_at)
        VALUES (?, ?, ?, ?, ?, 0, ?)
    """, (chat_id, symbol.upper(), float(target_price), condition.lower(), float(created_price), datetime.utcnow().isoformat()))
    alert_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return alert_id

def get_active_crypto_alerts() -> List[Dict[str, Any]]:
    """Retrieve all untriggered crypto price alerts."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, chat_id, symbol, target_price, condition, created_price, created_at
        FROM crypto_price_alerts
        WHERE is_triggered = 0
        ORDER BY id ASC
    """)
    rows = cursor.fetchall()
    conn.close()
    return [
        {
            "id": r[0],
            "chat_id": r[1],
            "symbol": r[2],
            "target_price": r[3],
            "condition": r[4],
            "created_price": r[5],
            "created_at": r[6]
        }
        for r in rows
    ]

def get_user_crypto_alerts(chat_id: int) -> List[Dict[str, Any]]:
    """Retrieve all active alerts set by a specific user."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, chat_id, symbol, target_price, condition, created_price, created_at
        FROM crypto_price_alerts
        WHERE chat_id = ? AND is_triggered = 0
        ORDER BY id DESC
    """, (chat_id,))
    rows = cursor.fetchall()
    conn.close()
    return [
        {
            "id": r[0],
            "chat_id": r[1],
            "symbol": r[2],
            "target_price": r[3],
            "condition": r[4],
            "created_price": r[5],
            "created_at": r[6]
        }
        for r in rows
    ]

def mark_crypto_alert_triggered(alert_id: int):
    """Mark a crypto price alert as triggered."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE crypto_price_alerts SET is_triggered = 1 WHERE id = ?", (alert_id,))
    conn.commit()
    conn.close()

def delete_crypto_alert(alert_id: int, chat_id: Optional[int] = None) -> bool:
    """Delete a crypto price alert by ID."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    if chat_id is not None:
        cursor.execute("DELETE FROM crypto_price_alerts WHERE id = ? AND chat_id = ?", (alert_id, chat_id))
    else:
        cursor.execute("DELETE FROM crypto_price_alerts WHERE id = ?", (alert_id,))
    affected = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return affected

# -------------------------------------------------------------
# Bot Settings & Music Storage Channel Management
# -------------------------------------------------------------

def get_bot_setting(key: str, default: Optional[str] = None) -> Optional[str]:
    """Retrieve a global bot setting from SQLite."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM bot_settings WHERE key = ?", (key,))
    row = cursor.fetchone()
    conn.close()
    if row and row[0]:
        return row[0]
    return default

def set_bot_setting(key: str, value: str) -> bool:
    """Save or update a global bot setting."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    now_str = datetime.utcnow().isoformat()
    cursor.execute("""
        INSERT INTO bot_settings (key, value, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
    """, (key, str(value).strip(), now_str))
    conn.commit()
    conn.close()
    return True

def delete_bot_setting(key: str) -> bool:
    """Delete a setting key."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM bot_settings WHERE key = ?", (key,))
    affected = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return affected

def get_music_channel() -> Optional[str]:
    """
    Get configured music archive channel (checks database first, then config.MUSIC_CHANNEL_ID).
    Returns clean channel target (e.g. '@mychannel' or '-1001234567890') or None.
    """
    db_val = get_bot_setting("music_channel_id")
    if db_val is not None:
        val = db_val.strip()
        if val and val.lower() not in ["none", "disabled", "null"]:
            return val
        return None

    from config import MUSIC_CHANNEL_ID
    if MUSIC_CHANNEL_ID and str(MUSIC_CHANNEL_ID).strip():
        val = str(MUSIC_CHANNEL_ID).strip()
        if val.lower() not in ["none", "disabled", "null"]:
            return val

    return None

def set_music_channel(channel_target: str) -> bool:
    """Save music storage channel in database."""
    target = channel_target.strip()
    return set_bot_setting("music_channel_id", target)

def remove_music_channel() -> bool:
    """Remove music storage channel configuration."""
    return set_bot_setting("music_channel_id", "DISABLED")

def log_music_archive(
    chat_id: int,
    query: str,
    title: str,
    performer: str,
    duration: int,
    file_id: str,
    channel_id: str,
    channel_message_id: Optional[int] = None
) -> bool:
    """Log an archived song that was stored in the channel."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    now_str = datetime.utcnow().isoformat()
    cursor.execute("""
        INSERT INTO music_archive (
            chat_id, query, title, performer, duration, file_id, channel_id, channel_message_id, archived_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        chat_id, query, title, performer, int(duration or 0),
        file_id, str(channel_id), channel_message_id, now_str
    ))
    conn.commit()
    conn.close()
    return True

def get_music_archive_stats() -> Dict[str, Any]:
    """Retrieve count and recent archived songs from channel storage."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM music_archive")
    total_count = cursor.fetchone()[0]

    cursor.execute("""
        SELECT title, performer, duration, channel_id, channel_message_id, archived_at
        FROM music_archive
        ORDER BY id DESC
        LIMIT 5
    """)
    rows = cursor.fetchall()
    conn.close()

    recent = [
        {
            "title": r[0],
            "performer": r[1],
            "duration": r[2],
            "channel_id": r[3],
            "channel_message_id": r[4],
            "archived_at": r[5]
        }
        for r in rows
    ]
    return {
        "total_archived": total_count,
        "recent": recent
    }

def save_media_token(token: str, url: str) -> bool:
    """Persist media URL token in SQLite so buttons work across bot restarts."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS media_tokens (
                token TEXT PRIMARY KEY,
                url TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        cursor.execute("""
            INSERT INTO media_tokens (token, url, created_at)
            VALUES (?, ?, ?)
            ON CONFLICT(token) DO UPDATE SET url = excluded.url, created_at = excluded.created_at
        """, (token, str(url).strip(), datetime.utcnow().isoformat()))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.warning(f"Failed to save media token {token}: {e}")
        return False

def get_media_token_url(token: str) -> Optional[str]:
    """Retrieve media URL associated with a token from SQLite."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT url FROM media_tokens WHERE token = ?", (token,))
        row = cursor.fetchone()
        conn.close()
        if row and row[0]:
            return row[0]
    except Exception as e:
        logger.warning(f"Failed to read media token {token}: {e}")
    return None




