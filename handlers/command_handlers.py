from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from config import BOT_TIMEZONE
from database import add_subscriber, remove_subscriber, is_subscribed
from services.holiday_calendar import (
    format_upcoming_message,
    format_calendar_message,
    format_alert_message,
    get_today_holiday,
    get_upcoming_holidays,
    get_current_cambodia_date
)

def get_main_menu_keyboard(chat_id: int) -> InlineKeyboardMarkup:
    """Build interactive inline menu buttons."""
    subscribed = is_subscribed(chat_id)
    alert_btn_text = "🔕 បិទការដាស់តឿន 4:00 AM" if subscribed else "🔔 បើកការដាស់តឿន 4:00 AM"
    alert_callback = "btn_unsubscribe" if subscribed else "btn_subscribe"
    
    keyboard = [
        [
            InlineKeyboardButton("🗓️ ថ្ងៃឈប់សម្រាកបន្ទាប់", callback_data="btn_upcoming"),
            InlineKeyboardButton("📅 ប្រតិទិនឆ្នាំ២០២៦", callback_data="btn_calendar_2026"),
        ],
        [
            InlineKeyboardButton(alert_btn_text, callback_data=alert_callback),
            InlineKeyboardButton("🧪 តេស្តដំណឹង (Test 4AM)", callback_data="btn_test_alert"),
        ],
        [
            InlineKeyboardButton("📥 របៀបទាញយកវីដេអូ", callback_data="btn_video_help"),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command."""
    chat = update.effective_chat
    user = update.effective_user
    
    # Auto-subscribe user on start by default
    add_subscriber(chat.id, user.username, chat.type)
    
    welcome_text = (
        f"👋 *សួស្តី {user.first_name}! សូមស្វាគមន៍មកកាន់ Smart Assistant Bot 🇰🇭*\n\n"
        "ខ្ញុំជាជំនួយការឆ្លាតវៃដែលអាចជួយលោកអ្នកក្នុងកិច្ចការដូចជា៖\n\n"
        "📥 *១. ទាញយកវីដេអូគ្រប់ប្រភេទ (All Video Downloader):*\n"
        "   - គ្រាន់តែ copy link ពី *TikTok, YouTube, Facebook, Instagram, Twitter/X...* រួចផ្ញើចូលទីនេះ នោះខ្ញុំនឹងទាញយកវីដេអូជូនភ្លាមៗ!\n\n"
        "🗓️ *២. ប្រតិទិនថ្ងៃឈប់សម្រាកបុណ្យជាតិ (Cambodia Holidays):*\n"
        "   - មើលកាលវិភាគឈប់សម្រាកការងារផ្លូវការ និងចំនួនថ្ងៃដែលនៅសល់។\n\n"
        "🔔 *៣. ការដាស់តឿនស្វ័យប្រវត្តិនាពេលទៀបភ្លឺ (៤:០០ ព្រឹក):*\n"
        "   - ផ្ញើសារជូនដំណឹង និងពាក្យជូនពរនៅម៉ោង ៤:០០ ព្រឹក នៅរាល់ថ្ងៃបុណ្យឈប់សម្រាក (បានបើកដំណើរការជាស្វ័យប្រវត្តិ ✅)។\n\n"
        "សូមជ្រើសរើសមុខងារខាងក្រោម៖"
    )
    
    await update.message.reply_text(
        welcome_text,
        reply_markup=get_main_menu_keyboard(chat.id),
        parse_mode="Markdown"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command."""
    help_text = (
        "💡 *បញ្ជី Command សម្រាប់ប្រើប្រាស់៖*\n\n"
        "🔹 `/start` - បើកផ្ទាំង Menu មេ\n"
        "🔹 `/upcoming` - មើលថ្ងៃបុណ្យដែលខិតជិតមកដល់\n"
        "🔹 `/calendar` - មើលប្រតិទិនឈប់សម្រាកប្រចាំឆ្នាំ (២០២៥, ២០២៦, ២០២៧)\n"
        "🔹 `/subscribe` - បើកការដាស់តឿនម៉ោង ៤:០០ ព្រឹក\n"
        "🔹 `/unsubscribe` - បិទការដាស់តឿន\n"
        "🔹 `/test_alert` - សាកល្បងសារដាស់តឿន ៤:០០ ព្រឹកឥឡូវនេះ\n"
        "🔹 `/status` - ពិនិត្យស្ថានភាពដាស់តឿន\n\n"
        "📥 *ការទាញយកវីដេអូ:* គ្រាន់តែ copy link (TikTok, YouTube, Facebook, ...) រួច paste ផ្ញើចូល Bot ជាការស្រេច!"
    )
    await update.message.reply_text(help_text, parse_mode="Markdown")

async def upcoming_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /upcoming command."""
    msg = format_upcoming_message()
    await update.message.reply_text(msg, parse_mode="Markdown")

async def calendar_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /calendar command."""
    current_year = datetime.now(BOT_TIMEZONE).year
    keyboard = [
        [
            InlineKeyboardButton("ឆ្នាំ ២០២៥", callback_data="btn_calendar_2025"),
            InlineKeyboardButton("ឆ្នាំ ២០២៦", callback_data="btn_calendar_2026"),
            InlineKeyboardButton("ឆ្នាំ ២០២៧", callback_data="btn_calendar_2027"),
        ]
    ]
    msg = format_calendar_message(current_year)
    await update.message.reply_text(
        msg,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

async def subscribe_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /subscribe command."""
    chat = update.effective_chat
    user = update.effective_user
    add_subscriber(chat.id, user.username, chat.type)
    await update.message.reply_text(
        "✅ *បានបើកការដាស់តឿនដោយជោគជ័យ!*\n\n"
        "Bot នឹងផ្ញើសារជូនដំណឹងនៅម៉ោង *៤:០០ ព្រឹក* (ម៉ោងនៅកម្ពុជា) រាល់ពេលមានថ្ងៃឈប់សម្រាកបុណ្យជាតិ 🇰🇭",
        parse_mode="Markdown"
    )

async def unsubscribe_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /unsubscribe command."""
    chat = update.effective_chat
    remove_subscriber(chat.id)
    await update.message.reply_text(
        "🔕 *បានបិទការដាស់តឿនបុណ្យជាតិរួចរាល់ហើយ។*\nអ្នកអាចបើកវិញបានគ្រប់ពេលដោយប្រើ `/subscribe`។",
        parse_mode="Markdown"
    )

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /status command."""
    chat_id = update.effective_chat.id
    subscribed = is_subscribed(chat_id)
    today_holiday = get_today_holiday()
    today_date = get_current_cambodia_date()
    
    status_text = (
        "📊 *ស្ថានភាពគណនីរបស់អ្នក (Bot Status):*\n\n"
        f"📅 កាលបរិច្ឆេទថ្ងៃនេះ: `{today_date}` (Asia/Phnom_Penh)\n"
        f"🔔 ការដាស់តឿន ៤:០០ ព្រឹក: {'✅ កំពុងបើក (Active)' if subscribed else '❌ បានបិទ (Inactive)'}\n"
        f"🎉 ថ្ងៃឈប់សម្រាកថ្ងៃនេះ: {today_holiday['name_km'] if today_holiday else 'ពុំមែនជាថ្ងៃឈប់សម្រាកទេ'}\n"
    )
    await update.message.reply_text(status_text, parse_mode="Markdown")

async def test_alert_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /test_alert command to preview the 4:00 AM alert."""
    upcoming = get_upcoming_holidays(limit=1)
    sample_holiday = upcoming[0] if upcoming else {
        "date": "2026-04-14",
        "name_km": "ពិធីបុណ្យចូលឆ្នាំថ្មីប្រពៃណីជាតិ",
        "name_en": "Khmer New Year",
        "wishes": "សួស្តីឆ្នាំថ្មីប្រពៃណីជាតិខ្មែរ! 🌸"
    }
    
    alert_text = (
        "🧪 *[សារតេស្តសាកល្បង - Preview 4:00 AM Alert]*\n\n"
        + format_alert_message(sample_holiday)
    )
    await update.message.reply_text(alert_text, parse_mode="Markdown")

async def button_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle inline button clicks."""
    query = update.callback_query
    await query.answer()
    data = query.data
    chat_id = query.message.chat_id
    
    if data == "btn_upcoming":
        msg = format_upcoming_message()
        await query.message.reply_text(msg, parse_mode="Markdown")
        
    elif data.startswith("btn_calendar_"):
        year = int(data.replace("btn_calendar_", ""))
        msg = format_calendar_message(year)
        await query.message.reply_text(msg, parse_mode="Markdown")
        
    elif data == "btn_subscribe":
        add_subscriber(chat_id, query.from_user.username, query.message.chat.type)
        await query.message.reply_text(
            "✅ *បានបើកការដាស់តឿនម៉ោង ៤:០០ ព្រឹកជោគជ័យ!*",
            parse_mode="Markdown"
        )
        await query.edit_message_reply_markup(reply_markup=get_main_menu_keyboard(chat_id))
        
    elif data == "btn_unsubscribe":
        remove_subscriber(chat_id)
        await query.message.reply_text(
            "🔕 *បានបិទការដាស់តឿនបុណ្យជាតិរួចរាល់ហើយ។*",
            parse_mode="Markdown"
        )
        await query.edit_message_reply_markup(reply_markup=get_main_menu_keyboard(chat_id))
        
    elif data == "btn_test_alert":
        upcoming = get_upcoming_holidays(limit=1)
        sample = upcoming[0] if upcoming else {
            "date": "2026-04-14",
            "name_km": "ពិធីបុណ្យចូលឆ្នាំថ្មីប្រពៃណីជាតិ",
            "name_en": "Khmer New Year",
            "wishes": "សួស្តីឆ្នាំថ្មីប្រពៃណីជាតិខ្មែរ! 🌸"
        }
        test_msg = "🧪 *[សារតេស្តសាកល្បង - 4:00 AM Alert]*\n\n" + format_alert_message(sample)
        await query.message.reply_text(test_msg, parse_mode="Markdown")
        
    elif data == "btn_video_help":
        help_msg = (
            "📥 *របៀបទាញយកវីដេអូ៖*\n\n"
            "1. ចូលទៅកាន់ TikTok, YouTube, Facebook, Instagram ឬ X/Twitter\n"
            "2. ចុចពាក្យ **Share** រួចជ្រើសរើស **Copy Link**\n"
            "3. ផ្ញើ (Paste) Link ចូលក្នុង Bot នេះភ្លាមៗ\n"
            "4. Bot នឹងទាញយកវីដេអូ និងផ្ញើចូល Telegram ជូនលោកអ្នកដោយស្វ័យប្រវត្ត!"
        )
        await query.message.reply_text(help_msg, parse_mode="Markdown")
