import os
from pathlib import Path
from dotenv import load_dotenv
import pytz

# Base Directories
BASE_DIR = Path(__file__).resolve().parent

# Load .env file explicitly from BASE_DIR
load_dotenv(dotenv_path=BASE_DIR / ".env")

# Telegram Bot Token
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") or "8747197308:AAG8Z1eXU-JQ6vrJ1EoyrIufqVZY1f3lm9g"

# Admin ID (for /broadcast command)
ADMIN_USER_ID = int(os.getenv("ADMIN_USER_ID", "1667275809"))

# AI Keys (Optional for AI Discussion)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") or "AQ.Ab8RN6JOdJTd2NrPJK_kpr5pfAYbinEFHX32jF6iJZeAek3tEA"
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# Timezone (Cambodia)
TIMEZONE_STR = os.getenv("BOT_TIMEZONE", "Asia/Phnom_Penh")
BOT_TIMEZONE = pytz.timezone(TIMEZONE_STR)

# Holiday Alert Scheduled Time (Default: 4:00 AM)
ALERT_HOUR = int(os.getenv("ALERT_HOUR", "4"))
ALERT_MINUTE = int(os.getenv("ALERT_MINUTE", "0"))

# Daily Weather Alert Scheduled Time (Default: 5:00 AM)
WEATHER_ALERT_HOUR = int(os.getenv("WEATHER_ALERT_HOUR", "5"))
WEATHER_ALERT_MINUTE = int(os.getenv("WEATHER_ALERT_MINUTE", "0"))

# Auto-Clean History Scheduled Times (Default: 12:00 PM Noon & 12:00 AM Midnight Cambodia Time)
AUTO_CLEAN_MIDNIGHT_HOUR = int(os.getenv("AUTO_CLEAN_MIDNIGHT_HOUR", "0"))
AUTO_CLEAN_MIDNIGHT_MINUTE = int(os.getenv("AUTO_CLEAN_MIDNIGHT_MINUTE", "0"))
AUTO_CLEAN_NOON_HOUR = int(os.getenv("AUTO_CLEAN_NOON_HOUR", "12"))
AUTO_CLEAN_NOON_MINUTE = int(os.getenv("AUTO_CLEAN_NOON_MINUTE", "0"))
# Backward compatibility aliases
AUTO_CLEAN_MORNING_HOUR = AUTO_CLEAN_MIDNIGHT_HOUR
AUTO_CLEAN_MORNING_MINUTE = AUTO_CLEAN_MIDNIGHT_MINUTE

# File size limits (Telegram bot upload limit is typically 50 MB, or 2000 MB with Local Bot API)
LOCAL_BOT_API_URL = os.getenv("LOCAL_BOT_API_URL", "").strip().rstrip("/")
MAX_FILE_SIZE_MB = int(os.getenv("MAX_FILE_SIZE_MB", "2000" if LOCAL_BOT_API_URL else "50"))

# Music Archive Storage Channel ID / Username (e.g. @Song182 or -1003994142170)
MUSIC_CHANNEL_ID = os.getenv("MUSIC_CHANNEL_ID") or os.getenv("SONG_CHANNEL_ID") or "-1003994142170"

# Base Directories
BASE_DIR = Path(__file__).resolve().parent
DOWNLOAD_DIR = BASE_DIR / "downloads"
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Database
DB_PATH = BASE_DIR / "bot_data.db"
