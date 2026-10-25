from datetime import datetime
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton
)
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
from services.ai_service import query_ai

def get_welcome_text(user_first_name: str) -> str:
    """Standard welcome message text for the dashboard."""
    return (
        f"🌟 *មជ្ឈមណ្ឌលជំនួយការឆ្លាតវៃ (Smart Assistant Hub)* 🇰🇭\n\n"
        f"👋 សួស្តី *{user_first_name}*! សូមជ្រើសរើសមុខងារដែលអ្នកត្រូវការប្រើប្រាស់ពី Menu ខាងក្រោម៖\n\n"
        "📥 *១. Video Downloader:* Copy link ពី TikTok, YouTube, Facebook, IG, X ផ្ញើចូលទីនេះភ្លាមៗ\n"
        "🗓️ *២. ប្រតិទិនបុណ្យជាតិ:* មើលថ្ងៃឈប់សម្រាកផ្លូវការ និងចំនួនថ្ងៃដែលនៅសល់\n"
        "⏰ *៣. ដាស់តឿន ៤:០០ ព្រឹក:* ជូនដំណឹងស្វ័យប្រវត្តិនាពេលទៀបភ្លឺរាល់ថ្ងៃឈប់សម្រាក\n"
        "✨ *៤. ជំនួយការ AI:* ជជែក ឬសួរសំណួរជាមួយ Gemini និង ChatGPT\n\n"
        "👇 _សូមចុចជ្រើសរើស Menu ខាងក្រោម៖_"
    )

def get_main_menu_keyboard(chat_id: int) -> InlineKeyboardMarkup:
    """Upgraded full-featured inline dashboard keyboard."""
    subscribed = is_subscribed(chat_id)
    alert_btn_text = "🔕 បិទដំណឹង 4:00 AM" if subscribed else "🔔 បើកដំណឹង 4:00 AM"
    alert_callback = "btn_unsubscribe" if subscribed else "btn_subscribe"
    
    keyboard = [
        [
            InlineKeyboardButton("📥 របៀបទាញយកវីដេអូ", callback_data="btn_video_help"),
            InlineKeyboardButton("🗓️ ប្រតិទិនបុណ្យជាតិ", callback_data="btn_calendar_2026"),
        ],
        [
            InlineKeyboardButton("⏳ ថ្ងៃបុណ្យបន្ទាប់", callback_data="btn_upcoming"),
            InlineKeyboardButton("📊 ស្ថានភាពគណនី", callback_data="btn_status"),
        ],
        [
            InlineKeyboardButton(alert_btn_text, callback_data=alert_callback),
            InlineKeyboardButton("🧪 តេស្តដំណឹង 4AM", callback_data="btn_test_alert"),
        ],
        [
            InlineKeyboardButton("✨ ជំនួយការ AI (Gemini/GPT)", callback_data="btn_ai_menu"),
            InlineKeyboardButton("💡 ការណែនាំ (Help)", callback_data="btn_help"),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_persistent_bottom_keyboard() -> ReplyKeyboardMarkup:
    """Persistent reply keyboard displayed at the bottom of the chat."""
    keyboard = [
        [KeyboardButton("📥 របៀបទាញយក"), KeyboardButton("🗓️ ប្រតិទិនបុណ្យជាតិ")],
        [KeyboardButton("⏳ ថ្ងៃបុណ្យបន្ទាប់"), KeyboardButton("🏠 ផ្ទាំង Menu មេ")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_back_keyboard() -> InlineKeyboardMarkup:
    """Standard back button returning to main menu."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 ត្រឡប់ទៅ Menu ដើម", callback_data="btn_back_main")]
    ])

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command with auto-cleanup and persistent keyboard."""
    chat = update.effective_chat
    user = update.effective_user
    
    # Auto-subscribe user on start
    add_subscriber(chat.id, user.username, chat.type)
    
    # Clean previous menu message if exists
    prev_menu_id = context.user_data.get('last_menu_id')
    if prev_menu_id:
        try:
            await context.bot.delete_message(chat_id=chat.id, message_id=prev_menu_id)
        except Exception:
            pass
            
    # Delete the user's /start command to keep chat clean
    try:
        await update.message.delete()
    except Exception:
        pass
        
    sent_msg = await context.bot.send_message(
        chat_id=chat.id,
        text=get_welcome_text(user.first_name),
        reply_markup=get_main_menu_keyboard(chat.id),
        parse_mode="Markdown"
    )
    context.user_data['last_menu_id'] = sent_msg.message_id

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command."""
    help_text = (
        "💡 *បញ្ជី Command សម្រាប់ប្រើប្រាស់៖*\n\n"
        "🔹 `/start` - បើកផ្ទាំង Dashboard មេ\n"
        "🔹 `/upcoming` - មើលថ្ងៃបុណ្យដែលខិតជិតមកដល់\n"
        "🔹 `/calendar` - មើលប្រតិទិនឈប់សម្រាកប្រចាំឆ្នាំ\n"
        "🔹 `/subscribe` - បើកការដាស់តឿនម៉ោង ៤:០០ ព្រឹក\n"
        "🔹 `/unsubscribe` - បិទការដាស់តឿន\n"
        "🔹 `/ask <សំណួរ>` - សួរសំណួរទៅកាន់ AI\n"
        "🔹 `/status` - ពិនិត្យស្ថានភាពគណនី\n"
        "🔹 `/test_alert` - សាកល្បងសារដាស់តឿន ៤:០០ ព្រឹក\n\n"
        "📥 *ការទាញយកវីដេអូ:* គ្រាន់តែ copy link (TikTok, YouTube, Facebook, ...) រួច paste ផ្ញើចូលទីនេះភ្លាមៗ!"
    )
    await update.message.reply_text(help_text, reply_markup=get_back_keyboard(), parse_mode="Markdown")

async def upcoming_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /upcoming command."""
    msg = format_upcoming_message()
    await update.message.reply_text(msg, reply_markup=get_back_keyboard(), parse_mode="Markdown")

async def calendar_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /calendar command."""
    current_year = datetime.now(BOT_TIMEZONE).year
    keyboard = [
        [
            InlineKeyboardButton("ឆ្នាំ ២០២៥", callback_data="btn_calendar_2025"),
            InlineKeyboardButton("ឆ្នាំ ២០២៦", callback_data="btn_calendar_2026"),
            InlineKeyboardButton("ឆ្នាំ ២០២៧", callback_data="btn_calendar_2027"),
        ],
        [
            InlineKeyboardButton("🔙 ត្រឡប់ទៅ Menu ដើម", callback_data="btn_back_main")
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
        reply_markup=get_back_keyboard(),
        parse_mode="Markdown"
    )

async def unsubscribe_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /unsubscribe command."""
    chat = update.effective_chat
    remove_subscriber(chat.id)
    await update.message.reply_text(
        "🔕 *បានបិទការដាស់តឿនបុណ្យជាតិរួចរាល់ហើយ។*\nអ្នកអាចបើកវិញបានគ្រប់ពេលដោយប្រើ `/subscribe`។",
        reply_markup=get_back_keyboard(),
        parse_mode="Markdown"
    )

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /status command."""
    chat_id = update.effective_chat.id
    user = update.effective_user
    subscribed = is_subscribed(chat_id)
    today_holiday = get_today_holiday()
    today_date = get_current_cambodia_date()
    
    status_text = (
        "📊 *ស្ថានភាពគណនីរបស់អ្នក (Account Status)*\n\n"
        f"👤 ឈ្មោះ: *{user.full_name}*\n"
        f"🆔 Telegram ID: `{chat_id}`\n"
        f"📅 កាលបរិច្ឆេទ: `{today_date}` (Asia/Phnom_Penh)\n"
        f"🔔 ការដាស់តឿន ៤:០០ ព្រឹក: {'✅ កំពុងបើក (Active)' if subscribed else '❌ បានបិទ (Inactive)'}\n"
        f"🎉 ថ្ងៃឈប់សម្រាកថ្ងៃនេះ: {today_holiday['name_km'] if today_holiday else 'ពុំមែនជាថ្ងៃឈប់សម្រាកទេ'}\n"
    )
    await update.message.reply_text(status_text, reply_markup=get_back_keyboard(), parse_mode="Markdown")

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
    await update.message.reply_text(alert_text, reply_markup=get_back_keyboard(), parse_mode="Markdown")

async def ask_ai_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /ask command for AI consultation."""
    user_query = " ".join(context.args) if context.args else ""
    if not user_query:
        await update.message.reply_text(
            "💡 *របៀបសួរ AI:*\nសូមវាយ `/ask <សំណួររបស់អ្នក>`\n\nឧទាហរណ៍៖ `/ask តើថ្ងៃចូលឆ្នាំខ្មែរមានប្រវត្តិយ៉ាងណា?`",
            parse_mode="Markdown"
        )
        return
        
    await update.message.chat.send_action("typing")
    response_text = await query_ai(user_query)
    await update.message.reply_text(response_text, parse_mode="Markdown")

async def button_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle inline button clicks with seamless in-place message editing."""
    query = update.callback_query
    data = query.data
    chat_id = query.message.chat_id
    user = query.from_user
    
    try:
        if data == "btn_upcoming":
            await query.answer()
            msg = format_upcoming_message()
            await query.edit_message_text(
                msg,
                reply_markup=get_back_keyboard(),
                parse_mode="Markdown"
            )
            
        elif data.startswith("btn_calendar_"):
            await query.answer()
            year = int(data.replace("btn_calendar_", ""))
            msg = format_calendar_message(year)
            keyboard = [
                [
                    InlineKeyboardButton("ឆ្នាំ ២០២៥", callback_data="btn_calendar_2025"),
                    InlineKeyboardButton("ឆ្នាំ ២០២៦", callback_data="btn_calendar_2026"),
                    InlineKeyboardButton("ឆ្នាំ ២០២៧", callback_data="btn_calendar_2027"),
                ],
                [
                    InlineKeyboardButton("🔙 ត្រឡប់ទៅ Menu ដើម", callback_data="btn_back_main")
                ]
            ]
            await query.edit_message_text(
                msg,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="Markdown"
            )
            
        elif data == "btn_status":
            await query.answer()
            subscribed = is_subscribed(chat_id)
            today_holiday = get_today_holiday()
            today_date = get_current_cambodia_date()
            status_text = (
                "📊 *ស្ថានភាពគណនីរបស់អ្នក (Account Status)*\n\n"
                f"👤 ឈ្មោះ: *{user.full_name}*\n"
                f"🆔 Telegram ID: `{chat_id}`\n"
                f"📅 កាលបរិច្ឆេទថ្ងៃនេះ: `{today_date}` (Asia/Phnom_Penh)\n"
                f"🔔 ការដាស់តឿន ៤:០០ ព្រឹក: {'✅ កំពុងបើក (Active)' if subscribed else '❌ បានបិទ (Inactive)'}\n"
                f"🎉 ថ្ងៃឈប់សម្រាកថ្ងៃនេះ: {today_holiday['name_km'] if today_holiday else 'ពុំមែនជាថ្ងៃឈប់សម្រាកទេ'}\n"
            )
            await query.edit_message_text(
                status_text,
                reply_markup=get_back_keyboard(),
                parse_mode="Markdown"
            )
            
        elif data == "btn_subscribe":
            add_subscriber(chat_id, user.username, query.message.chat.type)
            await query.answer("✅ បានបើកការដាស់តឿន ៤:០០ ព្រឹកជោគជ័យ!", show_alert=True)
            await query.edit_message_reply_markup(reply_markup=get_main_menu_keyboard(chat_id))
            
        elif data == "btn_unsubscribe":
            remove_subscriber(chat_id)
            await query.answer("🔕 បានបិទការដាស់តឿន ៤:០០ ព្រឹក!", show_alert=True)
            await query.edit_message_reply_markup(reply_markup=get_main_menu_keyboard(chat_id))
            
        elif data == "btn_test_alert":
            await query.answer()
            upcoming = get_upcoming_holidays(limit=1)
            sample = upcoming[0] if upcoming else {
                "date": "2026-04-14",
                "name_km": "ពិធីបុណ្យចូលឆ្នាំថ្មីប្រពៃណីជាតិ",
                "name_en": "Khmer New Year",
                "wishes": "សួស្តីឆ្នាំថ្មីប្រពៃណីជាតិខ្មែរ! 🌸"
            }
            test_msg = "🧪 *[សារតេស្តសាកល្បង - 4:00 AM Alert]*\n\n" + format_alert_message(sample)
            await query.edit_message_text(
                test_msg,
                reply_markup=get_back_keyboard(),
                parse_mode="Markdown"
            )
            
        elif data == "btn_video_help":
            await query.answer()
            help_msg = (
                "📥 *របៀបទាញយកវីដេអូ៖*\n\n"
                "1. ចូលទៅកាន់ TikTok, YouTube, Facebook, Instagram ឬ X/Twitter\n"
                "2. ចុចពាក្យ **Share** រួចជ្រើសរើស **Copy Link**\n"
                "3. ផ្ញើ (Paste) Link ចូលក្នុង Bot នេះភ្លាមៗ\n"
                "4. Bot នឹងទាញយកវីដេអូ និងផ្ញើជូនលោកអ្នកដោយស្វ័យប្រវត្ត!"
            )
            await query.edit_message_text(
                help_msg,
                reply_markup=get_back_keyboard(),
                parse_mode="Markdown"
            )
            
        elif data == "btn_ai_menu":
            await query.answer()
            ai_msg = (
                "✨ *ជំនួយការឆ្លាតវៃ AI (Gemini & ChatGPT)* 🤖\n\n"
                "លោកអ្នកអាចសួរនាំសំណួរ វិភាគទិន្នន័យ បកប្រែភាសា និងសរសេរអត្ថបទបានយ៉ាងរហ័ស!\n\n"
                "💡 *របៀបប្រើប្រាស់៖*\n"
                "• វាយ `/ask <សំណួររបស់អ្នក>` ដើម្បីសួរ AI ផ្ទាល់\n"
                "• ឧទាហរណ៍៖ `/ask សង្ខេបប្រវត្តិបុណ្យភ្ជុំបិណ្ឌ`\n\n"
                "_(គាំទ្រម៉ូដែល Google Gemini 2.5 Flash និង OpenAI GPT-4o)_"
            )
            await query.edit_message_text(
                ai_msg,
                reply_markup=get_back_keyboard(),
                parse_mode="Markdown"
            )
            
        elif data == "btn_help":
            await query.answer()
            help_msg = (
                "💡 *មជ្ឈមណ្ឌលជំនួយ និងការណែនាំ (Help Hub)*\n\n"
                "📥 *១. ការទាញយកវីដេអូ (Video Downloader):*\n"
                "• គាំទ្រ: TikTok (No Watermark), YouTube Shorts/Videos, Facebook Reels, Instagram, X/Twitter\n\n"
                "🗓️ *២. ប្រតិទិនបុណ្យជាតិ (Cambodia Holidays):*\n"
                "• រួមបញ្ចូលថ្ងៃឈប់សម្រាកផ្លូវការទាំងអស់នៅកម្ពុជា\n"
                "• ជូនដំណឹងស្វ័យប្រវត្តិនាពេលទៀបភ្លឺ ម៉ោង ៤:០០ ព្រឹក\n\n"
                "✨ *៣. បញ្ជា Command រហ័ស:*\n"
                "• `/start` - បើកផ្ទាំង Dashboard មេ\n"
                "• `/upcoming` - ថ្ងៃបុណ្យបន្ទាប់\n"
                "• `/calendar` - ប្រតិទិនប្រចាំឆ្នាំ\n"
                "• `/ask` - សួរសំណួរទៅ AI\n"
                "• `/status` - ពិនិត្យស្ថានភាពគណនី"
            )
            await query.edit_message_text(
                help_msg,
                reply_markup=get_back_keyboard(),
                parse_mode="Markdown"
            )
            
        elif data == "btn_back_main":
            await query.answer()
            user_name = user.first_name or "លោកអ្នក"
            await query.edit_message_text(
                get_welcome_text(user_name),
                reply_markup=get_main_menu_keyboard(chat_id),
                parse_mode="Markdown"
            )
    except Exception as e:
        try:
            await query.answer()
        except Exception:
            pass
