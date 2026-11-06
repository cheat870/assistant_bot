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
from telegram import BotCommand
from telegram.ext import (
    Application,
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
from services.health_server import start_health_server
from handlers.command_handlers import (
    start_command,
    help_command,
    upcoming_command,
    calendar_command,
    subscribe_command,
    unsubscribe_command,
    status_command,
    test_alert_command,
    ask_ai_command,
    weather_command,
    location_command,
    test_weather_command,
    finance_command,
    convert_command,
    remind_command,
    reminders_command,
    aimode_command,
    qr_command,
    broadcast_command,
    spend_command,
    income_command,
    budget_command,
    clear_expenses_command,
    speak_command,
    check_command,
    translate_command,
    song_command,
    rembg_command,
    sound_command,
    news_command,
    antispam_command,
    handle_voice_message,
    handle_photo_message,
    handle_location_message,
    button_callback_handler,
)
from handlers.video_handlers import handle_video_message

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

async def post_init(application: Application):
    """Register official commands in Telegram native menu button."""
    commands = [
        BotCommand("start", "🏠 ផ្ទាំង Dashboard មេ (Main Menu)"),
        BotCommand("budget", "📊 ចំណូល-ចំណាយ (Expense Tracker)"),
        BotCommand("spend", "💸 កត់ត្រាចំណាយ (Log Expense)"),
        BotCommand("income", "💰 កត់ត្រាចំណូល (Log Income)"),
        BotCommand("song", "🎧 ស្វែងរកចម្រៀង MP3 (Music Finder)"),
        BotCommand("speak", "🗣️ អានជាសំឡេង (Text-to-Speech)"),
        BotCommand("check", "✍️ ពិនិត្យអក្ខរាវិរុទ្ធខ្មែរ (Spellchecker)"),
        BotCommand("translate", "🌐 បកប្រែ Pro (English ⬄ Khmer)"),
        BotCommand("rembg", "✂️ កាត់ Background រូបភាព (Remove BG)"),
        BotCommand("news", "📰 ព័ត៌មានពេលព្រឹក (Morning News)"),
        BotCommand("finance", "💵 សេដ្ឋកិច្ច / មាស / សាំង (Finance & Rates)"),
        BotCommand("remind", "⏰ កំណត់សារដាស់តឿន (Set Reminder)"),
        BotCommand("reminders", "📋 បញ្ជីសារដាស់តឿន (Active Reminders)"),
        BotCommand("aimode", "🤖 បើក/បិទ AI Continuous Chat"),
        BotCommand("ask", "✨ សួរសំណួរ AI (Ask Gemini/GPT)"),
        BotCommand("qr", "🔲 បង្កើត QR Code (Generate QR)"),
        BotCommand("sound", "🔍 ស្វែងរកបទភ្លេង TikTok (Sound Finder)"),
        BotCommand("antispam", "🛡️ ការពារ Group (Group Anti-Spam)"),
        BotCommand("weather", "🌤️ អាកាសធាតុបច្ចុប្បន្ន (Weather Now)"),
        BotCommand("location", "📍 កំណត់ទីតាំងអាកាសធាតុ (Set Location)"),
        BotCommand("upcoming", "⏳ ថ្ងៃបុណ្យបន្ទាប់ (Upcoming Holidays)"),
        BotCommand("calendar", "📅 ប្រតិទិនបុណ្យជាតិ (Calendar)"),
        BotCommand("status", "📊 ស្ថានភាពគណនី (My Status)"),
        BotCommand("help", "💡 ការណែនាំប្រើប្រាស់ (Help & Guide)"),
    ]
    await application.bot.set_my_commands(commands)
    logger.info("Bot commands successfully registered to Telegram native Menu.")

def main():
    """Main application launcher."""
    print("=" * 60)
    print("🚀 Starting Telegram Assistant Bot (Video Downloader & Smart Hub)")
    print("=" * 60)
    
    if not BOT_TOKEN or BOT_TOKEN == "your_telegram_bot_token_here":
        print("\n❌ កំហុស៖ ពុំទាន់បានកំណត់ TELEGRAM_BOT_TOKEN នៅឡើយទេ!")
        print("សូមបើក file '.env' រួចដាក់ Token ដែលទទួលបានពី @BotFather\n")
        sys.exit(1)
        
    # Initialize SQLite Database
    init_db()
    logger.info("Database initialized successfully.")
    
    # Start HTTP Health Server for 24/7 Cloud Hosting (Render, Railway, Koyeb)
    start_health_server()
    
    # Build Telegram Application with generous timeouts for uploading large video files
    request_config = HTTPXRequest(
        connect_timeout=60.0,
        read_timeout=900.0,
        write_timeout=900.0,
        pool_timeout=60.0,
    )
    app = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .request(request_config)
        .post_init(post_init)
        .build()
    )
    
    # Register Core Command Handlers
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("weather", weather_command))
    app.add_handler(CommandHandler("location", location_command))
    app.add_handler(CommandHandler("test_weather", test_weather_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("upcoming", upcoming_command))
    app.add_handler(CommandHandler("calendar", calendar_command))
    app.add_handler(CommandHandler("holidays", calendar_command))
    app.add_handler(CommandHandler("subscribe", subscribe_command))
    app.add_handler(CommandHandler("unsubscribe", unsubscribe_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("test_alert", test_alert_command))
    app.add_handler(CommandHandler("ask", ask_ai_command))
    
    # Register New V2 Upgraded Command Handlers
    app.add_handler(CommandHandler("finance", finance_command))
    app.add_handler(CommandHandler("convert", convert_command))
    app.add_handler(CommandHandler("remind", remind_command))
    app.add_handler(CommandHandler("reminders", reminders_command))
    app.add_handler(CommandHandler("aimode", aimode_command))
    app.add_handler(CommandHandler("qr", qr_command))
    app.add_handler(CommandHandler("broadcast", broadcast_command))
    
    # Register V3 Upgraded Command Handlers (Expenses, TTS, Linguistics, Music, Rembg, News, Anti-Spam)
    app.add_handler(CommandHandler("budget", budget_command))
    app.add_handler(CommandHandler("spend", spend_command))
    app.add_handler(CommandHandler("income", income_command))
    app.add_handler(CommandHandler("clear_expenses", clear_expenses_command))
    app.add_handler(CommandHandler("speak", speak_command))
    app.add_handler(CommandHandler("voice", speak_command))
    app.add_handler(CommandHandler("check", check_command))
    app.add_handler(CommandHandler("translate", translate_command))
    app.add_handler(CommandHandler("tr", translate_command))
    app.add_handler(CommandHandler("song", song_command))
    app.add_handler(CommandHandler("music", song_command))
    app.add_handler(CommandHandler("rembg", rembg_command))
    app.add_handler(CommandHandler("sound", sound_command))
    app.add_handler(CommandHandler("identify", sound_command))
    app.add_handler(CommandHandler("news", news_command))
    app.add_handler(CommandHandler("antispam", antispam_command))
    
    # Register Callback Query Handler for Buttons
    app.add_handler(CallbackQueryHandler(button_callback_handler))

    # Register Location Handler for GPS Location Sharing
    app.add_handler(MessageHandler(filters.LOCATION, handle_location_message))
    
    # Register Voice & Audio Handler (Gemini Voice AI)
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, handle_voice_message))
    
    # Register Photo Handler (QR/KHQR & Gemini Vision OCR)
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo_message))

    # Register Message Handler for Videos, Links & Continuous AI Chat
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_video_message))
    
    # Register Daily Scheduler (4AM Holidays, 5AM Weather, Reminders)
    setup_scheduler(app)
    
    print("\n✅ Bot ដំណើរការរួចរាល់ហើយ! (Bot is running via polling...)")
    print("👉 ចូល Telegram រួចវាយពាក្យ /start ដើម្បីសាកល្បង។\n")
    
    # Start Polling
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
