import logging
import sys
import os
from pathlib import Path

# Add project root to sys.path so imports work from any working directory
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Ensure UTF-8 output on Windows console
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)
from telegram.request import HTTPXRequest

from config import BOT_TOKEN
from database import init_db
from services.scheduler import setup_scheduler
from handlers.command_handlers import (
    start_command,
    help_command,
    upcoming_command,
    calendar_command,
    subscribe_command,
    unsubscribe_command,
    status_command,
    test_alert_command,
    button_callback_handler,
)
from handlers.video_handlers import handle_video_message

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

def main():
    """Main application launcher."""
    print("=" * 60)
    print("🚀 Starting Telegram Assistant Bot (Video Downloader & Holiday Alert)")
    print("=" * 60)
    
    if not BOT_TOKEN or BOT_TOKEN == "your_telegram_bot_token_here":
        print("\n❌ កំហុស៖ ពុំទាន់បានកំណត់ TELEGRAM_BOT_TOKEN នៅឡើយទេ!")
        print("សូមបើក file '.env' រួចដាក់ Token ដែលទទួលបានពី @BotFather\n")
        sys.exit(1)
        
    # Initialize SQLite Database
    init_db()
    logger.info("Database initialized successfully.")
    
    # Build Telegram Application with generous timeouts for uploading large video files
    request_config = HTTPXRequest(
        connect_timeout=60.0,
        read_timeout=900.0,
        write_timeout=900.0,
        pool_timeout=60.0,
    )
    app = ApplicationBuilder().token(BOT_TOKEN).request(request_config).build()
    
    # Register Command Handlers
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("upcoming", upcoming_command))
    app.add_handler(CommandHandler("calendar", calendar_command))
    app.add_handler(CommandHandler("holidays", calendar_command))
    app.add_handler(CommandHandler("subscribe", subscribe_command))
    app.add_handler(CommandHandler("unsubscribe", unsubscribe_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("test_alert", test_alert_command))
    
    # Register Callback Query Handler for Buttons
    app.add_handler(CallbackQueryHandler(button_callback_handler))
    
    # Register Message Handler for Videos & Links
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_video_message))
    
    # Register Daily 4:00 AM Scheduler
    setup_scheduler(app)
    
    print("\n✅ Bot ដំណើរការរួចរាល់ហើយ! (Bot is running via polling...)")
    print("👉 ចូល Telegram រួចវាយពាក្យ /start ដើម្បីសាកល្បង។\n")
    
    # Start Polling
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
