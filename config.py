import os
from pathlib import Path
from dotenv import load_dotenv
import pytz

# Base Directories
BASE_DIR = Path(__file__).resolve().parent

# Load .env file explicitly from BASE_DIR
load_dotenv(dotenv_path=BASE_DIR / ".env")

# Telegram Bot Token
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")

# AI Keys (Optional for AI Discussion)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# Timezone (Cambodia)
TIMEZONE_STR = os.getenv("BOT_TIMEZONE", "Asia/Phnom_Penh")
BOT_TIMEZONE = pytz.timezone(TIMEZONE_STR)

# Holiday Alert Scheduled Time (Default: 4:00 AM)
ALERT_HOUR = int(os.getenv("ALERT_HOUR", "4"))
ALERT_MINUTE = int(os.getenv("ALERT_MINUTE", "0"))

# File size limits (Telegram bot upload limit is typically 50 MB)
MAX_FILE_SIZE_MB = int(os.getenv("MAX_FILE_SIZE_MB", "50"))

# Base Directories
BASE_DIR = Path(__file__).resolve().parent
DOWNLOAD_DIR = BASE_DIR / "downloads"
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Database
DB_PATH = BASE_DIR / "bot_data.db"
