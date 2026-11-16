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
    clean_chat_command,
    autoclean_command,
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
    pdf_command,
    handle_pdf_document,
    enhance_command,
    watermark_command,
    welcome_command,
    handle_new_chat_members,
    handle_voice_message,
    handle_photo_message,
    handle_document_image,
    handle_user_video_message,
    handle_location_message,
    memory_command,
    forget_command,
    search_command,
    briefing_command,
    compress_command,
    trip_command,
    car_command,
    code_command,
    run_code_command,
    debug_code_command,
    chart_command,
    excel_command,
    listen_podcast_command,
    chord_command,
    user_command,
    crypto_command,
    alert_command,
    alerts_list_command,
    content_command,
    setsongchannel_command,
    songchannel_command,
    clearsongchannel_command,
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
        BotCommand("briefing", "👑 សង្ខេបពេលព្រឹក VIP (Morning Briefing)"),
        BotCommand("compress", "🗜️ បង្រួម & បម្លែងឯកសារ (File Master)"),
        BotCommand("budget", "📊 ចំណូល-ចំណាយ (Expense Tracker)"),
        BotCommand("chart", "📊 ក្រាហ្វិកចំណាយ (Donut/Pie Chart)"),
        BotCommand("excel", "📈 ទាញយកប្រវត្តិចំណាយជា Excel"),
        BotCommand("listen", "🎧 Web Article ➔ Audio Podcast"),
        BotCommand("chord", "🎸 ស្វែងរក Chord ហ្គីតា/ព្យាណូ"),
        BotCommand("user", "👤 ស្វែងរក & បង្កើត Link Profile"),
        BotCommand("spend", "💸 កត់ត្រាចំណាយ (Log Expense)"),
        BotCommand("income", "💰 កត់ត្រាចំណូល (Log Income)"),
        BotCommand("song", "🎧 ស្វែងរកចម្រៀង MP3 (Music Finder)"),
        BotCommand("songchannel", "📻 ឃ្លាំងចម្រៀង Channel Storage"),
        BotCommand("pdf", "📄 Chat with PDF & សង្ខេបឯកសារ"),
        BotCommand("enhance", "🔍 ធ្វើឱ្យរូបច្បាស់ HD (Super-Res)"),
        BotCommand("watermark", "💧 ដាក់ Watermark ការពាររូបភាព"),
        BotCommand("welcome", "🖼️ Banner ស្វាគមន៍សមាជិក Group"),
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
        BotCommand("search", "🌐 ស្វែងរក Live Google Search Grounding"),
        BotCommand("memory", "🧠 ការចងចាំ Long-Term Memory"),
        BotCommand("forget", "🧹 លុបការចងចាំ AI (Reset Memory)"),
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
    try:
        await application.bot.set_my_commands(commands)
        logger.info("Bot commands successfully registered to Telegram native Menu.")
    except Exception as e_cmd:
        logger.warning(f"Could not register Telegram native Menu commands: {e_cmd}")

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
    app.add_handler(CommandHandler("start", start_command, block=False))
    app.add_handler(CommandHandler("weather", weather_command, block=False))
    app.add_handler(CommandHandler("location", location_command, block=False))
    app.add_handler(CommandHandler("test_weather", test_weather_command, block=False))
    app.add_handler(CommandHandler("help", help_command, block=False))
    app.add_handler(CommandHandler("upcoming", upcoming_command, block=False))
    app.add_handler(CommandHandler("calendar", calendar_command, block=False))
    app.add_handler(CommandHandler("holidays", calendar_command, block=False))
    app.add_handler(CommandHandler("subscribe", subscribe_command, block=False))
    app.add_handler(CommandHandler("unsubscribe", unsubscribe_command, block=False))
    app.add_handler(CommandHandler("status", status_command, block=False))
    app.add_handler(CommandHandler("test_alert", test_alert_command, block=False))
    app.add_handler(CommandHandler("ask", ask_ai_command, block=False))
    
    # Register New V2 Upgraded Command Handlers
    app.add_handler(CommandHandler("finance", finance_command, block=False))
    app.add_handler(CommandHandler("convert", convert_command, block=False))
    app.add_handler(CommandHandler("remind", remind_command, block=False))
    app.add_handler(CommandHandler("reminders", reminders_command, block=False))
    app.add_handler(CommandHandler("clean", clean_chat_command, block=False))
    app.add_handler(CommandHandler("clear", clean_chat_command, block=False))
    app.add_handler(CommandHandler("autoclean", autoclean_command, block=False))
    app.add_handler(CommandHandler("autodelete", autoclean_command, block=False))
    app.add_handler(CommandHandler("aimode", aimode_command, block=False))
    app.add_handler(CommandHandler("qr", qr_command, block=False))
    app.add_handler(CommandHandler("broadcast", broadcast_command, block=False))
    
    # Register V3 Upgraded Command Handlers (Expenses, TTS, Linguistics, Music, Rembg, News, Anti-Spam)
    app.add_handler(CommandHandler("budget", budget_command, block=False))
    app.add_handler(CommandHandler("spend", spend_command, block=False))
    app.add_handler(CommandHandler("income", income_command, block=False))
    app.add_handler(CommandHandler("clear_expenses", clear_expenses_command, block=False))
    app.add_handler(CommandHandler("speak", speak_command, block=False))
    app.add_handler(CommandHandler("voice", speak_command, block=False))
    app.add_handler(CommandHandler("check", check_command, block=False))
    app.add_handler(CommandHandler("translate", translate_command, block=False))
    app.add_handler(CommandHandler("tr", translate_command, block=False))
    app.add_handler(CommandHandler("song", song_command, block=False))
    app.add_handler(CommandHandler("music", song_command, block=False))
    app.add_handler(CommandHandler("rembg", rembg_command, block=False))
    app.add_handler(CommandHandler("sound", sound_command, block=False))
    app.add_handler(CommandHandler("identify", sound_command, block=False))
    app.add_handler(CommandHandler("news", news_command, block=False))
    app.add_handler(CommandHandler("antispam", antispam_command, block=False))
    
    # Register V4 Pro Upgraded Command Handlers (PDF, Enhancer, Watermark, Welcome)
    app.add_handler(CommandHandler("pdf", pdf_command, block=False))
    app.add_handler(CommandHandler("enhance", enhance_command, block=False))
    app.add_handler(CommandHandler("upscale", enhance_command, block=False))
    app.add_handler(CommandHandler("watermark", watermark_command, block=False))
    app.add_handler(CommandHandler("welcome", welcome_command, block=False))

    # Register V5 Master Level Handlers (Long-Term Vector Memory, Real-Time Search, Briefing, File Master)
    app.add_handler(CommandHandler("memory", memory_command, block=False))
    app.add_handler(CommandHandler("forget", forget_command, block=False))
    app.add_handler(CommandHandler("search", search_command, block=False))
    app.add_handler(CommandHandler("briefing", briefing_command, block=False))
    app.add_handler(CommandHandler("compress", compress_command, block=False))
    
    # CamRoad Trip Planner & Car Diagnostic
    app.add_handler(CommandHandler("trip", trip_command, block=False))
    app.add_handler(CommandHandler("travel", trip_command, block=False))
    app.add_handler(CommandHandler("car", car_command, block=False))

    # Code Runner Sandbox & AI Debugger
    app.add_handler(CommandHandler("code", code_command, block=False))
    app.add_handler(CommandHandler("run", run_code_command, block=False))
    app.add_handler(CommandHandler("debug", debug_code_command, block=False))

    # Receipt, Budget Chart & Excel
    app.add_handler(CommandHandler("chart", chart_command, block=False))
    app.add_handler(CommandHandler("excel", excel_command, block=False))

    # Web Article to Audio Podcast
    app.add_handler(CommandHandler("listen", listen_podcast_command, block=False))
    app.add_handler(CommandHandler("podcast", listen_podcast_command, block=False))

    # Music Chords & Song Finder
    app.add_handler(CommandHandler("chord", chord_command, block=False))
    app.add_handler(CommandHandler("setsongchannel", setsongchannel_command, block=False))
    app.add_handler(CommandHandler("setmusicchannel", setsongchannel_command, block=False))
    app.add_handler(CommandHandler("songchannel", songchannel_command, block=False))
    app.add_handler(CommandHandler("musicchannel", songchannel_command, block=False))
    app.add_handler(CommandHandler("clearsongchannel", clearsongchannel_command, block=False))
    app.add_handler(CommandHandler("delsongchannel", clearsongchannel_command, block=False))

    # Telegram Profile Resolver (1-Click Chat Link Generator)
    app.add_handler(CommandHandler("user", user_command, block=False))
    app.add_handler(CommandHandler("whois", user_command, block=False))
    app.add_handler(CommandHandler("profile", user_command, block=False))

    # Crypto, TON & Gold Live Price Watcher
    app.add_handler(CommandHandler("crypto", crypto_command, block=False))
    app.add_handler(CommandHandler("coin", crypto_command, block=False))
    app.add_handler(CommandHandler("ton", crypto_command, block=False))
    app.add_handler(CommandHandler("btc", crypto_command, block=False))
    app.add_handler(CommandHandler("alert", alert_command, block=False))
    app.add_handler(CommandHandler("alerts", alerts_list_command, block=False))
    app.add_handler(CommandHandler("myalerts", alerts_list_command, block=False))

    # AI Content Creator Studio (Facebook, TikTok & Hashtags)
    app.add_handler(CommandHandler("content", content_command, block=False))
    app.add_handler(CommandHandler("caption", content_command, block=False))
    app.add_handler(CommandHandler("post", content_command, block=False))
    app.add_handler(CommandHandler("script", content_command, block=False))
    
    # Register Callback Query Handler for Buttons
    app.add_handler(CallbackQueryHandler(button_callback_handler, block=False))

    # Register Location Handler for GPS Location Sharing
    app.add_handler(MessageHandler(filters.LOCATION, handle_location_message, block=False))

    # Register PDF Document Handler (Chat with PDF & Summarizer)
    app.add_handler(MessageHandler(filters.Document.PDF | filters.Document.MimeType("application/pdf"), handle_pdf_document, block=False))

    # Register Uncompressed Document Image Handler (EXIF GPS Extraction)
    app.add_handler(MessageHandler(
        filters.Document.IMAGE | filters.Document.MimeType("image/jpeg") | filters.Document.MimeType("image/png") | filters.Document.MimeType("image/webp"),
        handle_document_image,
        block=False
    ))

    # Register New Chat Members Handler (Custom Welcome Banner)
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, handle_new_chat_members, block=False))
    
    # Register Voice & Audio Handler (Gemini Voice AI)
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, handle_voice_message, block=False))
    
    # Register Photo Handler (QR/KHQR & Gemini Vision OCR)
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo_message, block=False))

    # Register User Video Handler (Video Geolocation AI & Video Tools)
    app.add_handler(MessageHandler(filters.VIDEO | filters.ANIMATION | filters.VIDEO_NOTE, handle_user_video_message, block=False))

    # Register Message Handler for Videos, Links & Continuous AI Chat
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_video_message, block=False))
    
    # Register Daily Scheduler (4AM Holidays, 5AM Weather, Reminders)
    setup_scheduler(app)
    
    print("\n✅ Bot ដំណើរការរួចរាល់ហើយ! (Bot is running via polling...)")
    print("👉 ចូល Telegram រួចវាយពាក្យ /start ដើម្បីសាកល្បង។\n")
    
    # Start Polling with infinite bootstrap retries so temporary 502/network errors from Telegram never crash the container
    import time
    while True:
        try:
            app.run_polling(
                drop_pending_updates=False,
                bootstrap_retries=-1,
                timeout=20,
            )
            break
        except Exception as e_poll:
            logger.warning(f"Polling loop encountered network glitch: {e_poll}. Retrying in 3 seconds...")
            time.sleep(3)

if __name__ == "__main__":
    main()
