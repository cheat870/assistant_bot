from datetime import datetime
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton
)
from telegram.ext import ContextTypes

from config import BOT_TIMEZONE, WEATHER_ALERT_HOUR, ALERT_HOUR
from database import (
    add_subscriber,
    remove_subscriber,
    is_subscribed,
    get_user_weather_settings,
    set_user_location,
    set_weather_alert_active,
)
from services.holiday_calendar import (
    format_upcoming_message,
    format_calendar_message,
    format_alert_message,
    get_today_holiday,
    get_upcoming_holidays,
    get_current_cambodia_date
)
from services.weather_service import (
    fetch_weather,
    format_weather_message,
    reverse_geocode_async,
    DEFAULT_LAT,
    DEFAULT_LON,
    DEFAULT_LOCATION_NAME,
)
from services.ai_service import query_ai

# Preset Cambodian Provinces (Coordinates & Khmer Names)
PROVINCE_PRESETS = {
    "phnompenh": {"name": "រាជធានីភ្នំពេញ", "lat": 11.5564, "lon": 104.9282},
    "siemreap": {"name": "ខេត្តសៀមរាប", "lat": 13.3671, "lon": 103.8448},
    "battambang": {"name": "ខេត្តបាត់ដំបង", "lat": 13.0957, "lon": 103.2022},
    "sihanoukville": {"name": "ខេត្តព្រះសីហនុ", "lat": 10.6275, "lon": 103.5221},
    "kampot": {"name": "ខេត្តកំពត", "lat": 10.6104, "lon": 104.1815},
    "kandal": {"name": "ខេត្តកណ្ដាល", "lat": 11.4588, "lon": 104.9458},
}

def get_welcome_text(user_first_name: str) -> str:
    """Standard welcome message text for the dashboard."""
    return (
        f"🌟 *មជ្ឈមណ្ឌលជំនួយការឆ្លាតវៃ (Smart Assistant Hub)* 🇰🇭\n\n"
        f"👋 សួស្តី *{user_first_name}*! សូមជ្រើសរើសមុខងារដែលអ្នកត្រូវការប្រើប្រាស់ពី Menu ខាងក្រោម៖\n\n"
        "📥 *១. Video Downloader:* Copy link ពី TikTok, YouTube, Facebook, IG, X ផ្ញើចូលទីនេះភ្លាមៗ\n"
        "🗓️ *២. ប្រតិទិនបុណ្យជាតិ:* មើលថ្ងៃឈប់សម្រាកផ្លូវការ និងចំនួនថ្ងៃដែលនៅសល់\n"
        "⏰ *៣. ដាស់តឿន ៤:០០ ព្រឹក:* ជូនដំណឹងស្វ័យប្រវត្តិនាពេលទៀបភ្លឺរាល់ថ្ងៃឈប់សម្រាកបុណ្យជាតិ\n"
        "🌤️ *៤. ដំណឹងអាកាសធាតុ ៥:០០ ព្រឹក:* ផ្ញើរបាយការណ៍អាកាសធាតុនៅទីតាំងរបស់អ្នករាល់ព្រឹកជារៀងរាល់ថ្ងៃ\n"
        "✨ *៥. ជំនួយការ AI:* ជជែក ឬសួរសំណួរជាមួយ Gemini និង ChatGPT\n\n"
        "👇 _សូមចុចជ្រើសរើស Menu ខាងក្រោម៖_"
    )

def get_main_menu_keyboard(chat_id: int) -> InlineKeyboardMarkup:
    """Upgraded 10-button full-featured inline dashboard keyboard."""
    holiday_sub = is_subscribed(chat_id)
    holiday_btn_text = "🔕 បិទដំណឹង 4:00 AM" if holiday_sub else "🔔 បើកដំណឹង 4:00 AM"
    holiday_callback = "btn_unsubscribe" if holiday_sub else "btn_subscribe"
    
    w_settings = get_user_weather_settings(chat_id)
    weather_active = w_settings.get("is_active", True)
    loc_name = w_settings.get("location_name", "ភ្នំពេញ")
    weather_btn_text = "🔕 បិទអាកាសធាតុ 5AM" if weather_active else "🌅 បើកអាកាសធាតុ 5AM"
    weather_callback = "btn_toggle_weather_off" if weather_active else "btn_toggle_weather_on"
    
    keyboard = [
        [
            InlineKeyboardButton("📥 របៀបទាញយកវីដេអូ", callback_data="btn_video_help"),
            InlineKeyboardButton("🗓️ ប្រតិទិនបុណ្យជាតិ", callback_data="btn_calendar_2026"),
        ],
        [
            InlineKeyboardButton("⏳ ថ្ងៃបុណ្យបន្ទាប់", callback_data="btn_upcoming"),
            InlineKeyboardButton("🌤️ អាកាសធាតុថ្ងៃនេះ", callback_data="btn_weather_now"),
        ],
        [
            InlineKeyboardButton(holiday_btn_text, callback_data=holiday_callback),
            InlineKeyboardButton(weather_btn_text, callback_data=weather_callback),
        ],
        [
            InlineKeyboardButton(f"📍 ទីតាំង: {loc_name[:10]}", callback_data="btn_location_menu"),
            InlineKeyboardButton("📊 ស្ថានភាពគណនី", callback_data="btn_status"),
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
        [KeyboardButton("🌤️ អាកាសធាតុ"), KeyboardButton("📍 ផ្ញើទីតាំង GPS", request_location=True)],
        [KeyboardButton("📥 របៀបទាញយក"), KeyboardButton("🗓️ ប្រតិទិនបុណ្យជាតិ")],
        [KeyboardButton("⏳ ថ្ងៃបុណ្យបន្ទាប់"), KeyboardButton("🏠 ផ្ទាំង Menu មេ")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_back_keyboard() -> InlineKeyboardMarkup:
    """Standard back button returning to main menu."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 ត្រឡប់ទៅ Menu ដើម", callback_data="btn_back_main")]
    ])

def get_location_selection_keyboard() -> InlineKeyboardMarkup:
    """Keyboard for selecting provinces or GPS location."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🏙️ រាជធានីភ្នំពេញ", callback_data="setloc_phnompenh"),
            InlineKeyboardButton("🏛️ ខេត្តសៀមរាប", callback_data="setloc_siemreap"),
        ],
        [
            InlineKeyboardButton("🌾 ខេត្តបាត់ដំបង", callback_data="setloc_battambang"),
            InlineKeyboardButton("🏖️ ខេត្តព្រះសីហនុ", callback_data="setloc_sihanoukville"),
        ],
        [
            InlineKeyboardButton("⛰️ ខេត្តកំពត", callback_data="setloc_kampot"),
            InlineKeyboardButton("🏞️ ខេត្តកណ្ដាល", callback_data="setloc_kandal"),
        ],
        [
            InlineKeyboardButton("🔄 តេស្តដំណឹង 5AM", callback_data="btn_test_weather"),
            InlineKeyboardButton("🔙 ត្រឡប់ទៅ Menu ដើម", callback_data="btn_back_main"),
        ]
    ])

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command with auto-cleanup and persistent keyboard."""
    chat = update.effective_chat
    user = update.effective_user
    
    # Auto-subscribe user to holiday and weather alerts on start
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
    
    # Also attach bottom persistent keyboard for easy navigation
    try:
        await context.bot.send_message(
            chat_id=chat.id,
            text="📱 _ចុច Menu ឬប៊ូតុងខាងក្រោមសម្រាប់បញ្ជា Bot:_ ",
            reply_markup=get_persistent_bottom_keyboard(),
            parse_mode="Markdown"
        )
    except Exception:
        pass

async def weather_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /weather command to check weather immediately."""
    chat_id = update.effective_chat.id
    settings = get_user_weather_settings(chat_id)
    lat = settings.get("latitude", DEFAULT_LAT)
    lon = settings.get("longitude", DEFAULT_LON)
    loc_name = settings.get("location_name", DEFAULT_LOCATION_NAME)
    
    await update.message.chat.send_action("typing")
    w_data = await fetch_weather(lat, lon)
    if not w_data:
        await update.message.reply_text("❌ មិនអាចទាញយកព័ត៌មានអាកាសធាតុបានទេ សូមព្យាយាមម្តងទៀត។")
        return
        
    msg = format_weather_message(w_data, loc_name, is_daily_alert=False)
    await update.message.reply_text(
        msg,
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton("📍 ប្ដូរទីតាំង", callback_data="btn_location_menu"),
                InlineKeyboardButton("🔙 Menu ដើម", callback_data="btn_back_main")
            ]
        ]),
        parse_mode="Markdown"
    )

async def location_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /location command to configure weather location."""
    chat_id = update.effective_chat.id
    settings = get_user_weather_settings(chat_id)
    loc_name = settings.get("location_name", DEFAULT_LOCATION_NAME)
    
    text = (
        "📍 *កំណត់ទីតាំងសម្រាប់ដំណឹងអាកាសធាតុ ៥:០០ ព្រឹក*\n\n"
        f"ទីតាំងបច្ចុប្បន្នរបស់អ្នក៖ *{loc_name}*\n\n"
        "👉 *ជម្រើសទី ១:* ចុចប៊ូតុង **📍 ផ្ញើទីតាំង GPS** នៅលើក្ដារចុចខាងក្រោមដើម្បីកំណត់ទីតាំងស្វ័យប្រវត្តិតាមរយៈ GPS\n"
        "👉 *ជម្រើសទី ២:* ចុចជ្រើសរើសរាជធានី-ខេត្តខាងក្រោមនេះ៖"
    )
    await update.message.reply_text(
        text,
        reply_markup=get_location_selection_keyboard(),
        parse_mode="Markdown"
    )

async def test_weather_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /test_weather command to preview 5:00 AM daily alert."""
    chat_id = update.effective_chat.id
    settings = get_user_weather_settings(chat_id)
    lat = settings.get("latitude", DEFAULT_LAT)
    lon = settings.get("longitude", DEFAULT_LON)
    loc_name = settings.get("location_name", DEFAULT_LOCATION_NAME)
    
    await update.message.chat.send_action("typing")
    w_data = await fetch_weather(lat, lon)
    if not w_data:
        await update.message.reply_text("❌ មិនអាចទាញយកព័ត៌មានអាកាសធាតុបានទេ។")
        return
        
    msg = (
        "🧪 *[សារតេស្តសាកល្បង - 5:00 AM Weather Alert Preview]*\n\n"
        + format_weather_message(w_data, loc_name, is_daily_alert=True)
    )
    await update.message.reply_text(msg, reply_markup=get_back_keyboard(), parse_mode="Markdown")

async def handle_location_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle GPS location sent by user."""
    loc = update.message.location
    if not loc:
        return
        
    chat = update.effective_chat
    lat = loc.latitude
    lon = loc.longitude
    
    await chat.send_action("typing")
    loc_name = await reverse_geocode_async(lat, lon)
    
    # Save location and ensure 5:00 AM alert is enabled
    set_user_location(chat.id, lat, lon, loc_name)
    set_weather_alert_active(chat.id, True)
    
    w_data = await fetch_weather(lat, lon)
    weather_text = format_weather_message(w_data, loc_name, is_daily_alert=False) if w_data else ""
    
    reply_text = (
        f"✅ *បានកត់ត្រាទីតាំងរបស់អ្នកជោគជ័យ!* 📍\n\n"
        f"🏢 ទីតាំង៖ *{loc_name}*\n"
        f"🌐 កូអរដោនេ៖ `{lat:.4f}, {lon:.4f}`\n\n"
        f"🌅 *Bot នឹងផ្ញើរបាយការណ៍អាកាសធាតុនៅទីតាំងនេះជូនអ្នករាល់ព្រឹកនៅម៉ោង ៥:០០ ព្រឹកជារៀងរាល់ថ្ងៃ!*\n\n"
        f"---\n"
        f"{weather_text}"
    )
    await update.message.reply_text(
        reply_text,
        reply_markup=get_back_keyboard(),
        parse_mode="Markdown"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command."""
    help_text = (
        "💡 *បញ្ជី Command សម្រាប់ប្រើប្រាស់៖*\n\n"
        "🔹 `/start` - បើកផ្ទាំង Dashboard មេ\n"
        "🔹 `/weather` - មើលអាកាសធាតុបច្ចុប្បន្ន\n"
        "🔹 `/location` - កំណត់ទីតាំងសម្រាប់ដំណឹង 5AM\n"
        "🔹 `/upcoming` - មើលថ្ងៃបុណ្យដែលខិតជិតមកដល់\n"
        "🔹 `/calendar` - មើលប្រតិទិនឈប់សម្រាកប្រចាំឆ្នាំ\n"
        "🔹 `/subscribe` - បើកការដាស់តឿនបុណ្យជាតិ ៤:០០ ព្រឹក\n"
        "🔹 `/unsubscribe` - បិទការដាស់តឿនបុណ្យជាតិ\n"
        "🔹 `/ask <សំណួរ>` - សួរសំណួរទៅកាន់ AI (Gemini/GPT)\n"
        "🔹 `/status` - ពិនិត្យស្ថានភាពគណនី\n"
        "🔹 `/test_weather` - សាកល្បងសារអាកាសធាតុ ៥:០០ ព្រឹក\n"
        "🔹 `/test_alert` - សាកល្បងសារបុណ្យជាតិ ៤:០០ ព្រឹក\n\n"
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
    
    w_settings = get_user_weather_settings(chat_id)
    loc_name = w_settings.get("location_name", "ភ្នំពេញ")
    weather_active = w_settings.get("is_active", True)
    
    status_text = (
        "📊 *ស្ថានភាពគណនីរបស់អ្នក (Account Status)*\n\n"
        f"👤 ឈ្មោះ: *{user.full_name}*\n"
        f"🆔 Telegram ID: `{chat_id}`\n"
        f"📅 កាលបរិច្ឆេទ: `{today_date}` (Asia/Phnom_Penh)\n"
        f"📍 ទីតាំងអាកាសធាតុ: *{loc_name}*\n"
        f"🌅 ដំណឹងអាកាសធាតុ ៥:០០ ព្រឹក: {'✅ កំពុងបើក (Active)' if weather_active else '❌ បានបិទ (Inactive)'}\n"
        f"🔔 ដំណឹងបុណ្យជាតិ ៤:០០ ព្រឹក: {'✅ កំពុងបើក (Active)' if subscribed else '❌ បានបិទ (Inactive)'}\n"
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
            
        elif data == "btn_weather_now":
            await query.answer("កំពុងទាញយកព័ត៌មានអាកាសធាតុ...")
            w_settings = get_user_weather_settings(chat_id)
            lat = w_settings.get("latitude", DEFAULT_LAT)
            lon = w_settings.get("longitude", DEFAULT_LON)
            loc_name = w_settings.get("location_name", DEFAULT_LOCATION_NAME)
            
            w_data = await fetch_weather(lat, lon)
            if w_data:
                msg = format_weather_message(w_data, loc_name, is_daily_alert=False)
            else:
                msg = "❌ មិនអាចទាញយកព័ត៌មានអាកាសធាតុបានទេ។ សូមសាកល្បងម្ដងទៀត។"
                
            await query.edit_message_text(
                msg,
                reply_markup=InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton("🔄 ធ្វើបច្ចុប្បន្នភាព", callback_data="btn_weather_now"),
                        InlineKeyboardButton("📍 ប្ដូរទីតាំង", callback_data="btn_location_menu"),
                    ],
                    [
                        InlineKeyboardButton("🔙 ត្រឡប់ទៅ Menu ដើម", callback_data="btn_back_main")
                    ]
                ]),
                parse_mode="Markdown"
            )
            
        elif data == "btn_location_menu":
            await query.answer()
            w_settings = get_user_weather_settings(chat_id)
            loc_name = w_settings.get("location_name", DEFAULT_LOCATION_NAME)
            text = (
                "📍 *កំណត់ទីតាំងសម្រាប់ដំណឹងអាកាសធាតុ ៥:០០ ព្រឹក*\n\n"
                f"ទីតាំងបច្ចុប្បន្នរបស់អ្នក៖ *{loc_name}*\n\n"
                "👉 សូមជ្រើសរើសរាជធានី-ខេត្តដែលអ្នករស់នៅ ឬចុចប៊ូតុង **📍 ផ្ញើទីតាំង GPS** នៅលើក្ដារចុចទូរស័ព្ទខាងក្រោម៖"
            )
            await query.edit_message_text(
                text,
                reply_markup=get_location_selection_keyboard(),
                parse_mode="Markdown"
            )
            
        elif data.startswith("setloc_"):
            prov_key = data.replace("setloc_", "")
            prov_info = PROVINCE_PRESETS.get(prov_key)
            if prov_info:
                set_user_location(chat_id, prov_info["lat"], prov_info["lon"], prov_info["name"])
                set_weather_alert_active(chat_id, True)
                await query.answer(f"✅ បានកំណត់ទីតាំង៖ {prov_info['name']}!", show_alert=True)
                
                # Show updated weather for selected province
                w_data = await fetch_weather(prov_info["lat"], prov_info["lon"])
                if w_data:
                    msg = (
                        f"✅ *បានកំណត់ទីតាំងជោគជ័យ!* 📍 *{prov_info['name']}*\n\n"
                        f"🌅 *Bot នឹងផ្ញើរបាយការណ៍អាកាសធាតុនៅទីតាំងនេះជូនអ្នករាល់ព្រឹកម៉ោង ៥:០០ ព្រឹក!*\n\n"
                        f"---\n"
                        + format_weather_message(w_data, prov_info["name"], is_daily_alert=False)
                    )
                else:
                    msg = f"✅ បានកំណត់ទីតាំង៖ *{prov_info['name']}* រួចរាល់ហើយ!"
                    
                await query.edit_message_text(
                    msg,
                    reply_markup=InlineKeyboardMarkup([
                        [
                            InlineKeyboardButton("📍 ប្ដូរទីតាំងផ្សេង", callback_data="btn_location_menu"),
                            InlineKeyboardButton("🔙 Menu ដើម", callback_data="btn_back_main")
                        ]
                    ]),
                    parse_mode="Markdown"
                )
                
        elif data == "btn_toggle_weather_on":
            set_weather_alert_active(chat_id, True)
            await query.answer("🌅 បានបើកដំណឹងអាកាសធាតុ ៥:០០ ព្រឹកជោគជ័យ!", show_alert=True)
            await query.edit_message_reply_markup(reply_markup=get_main_menu_keyboard(chat_id))
            
        elif data == "btn_toggle_weather_off":
            set_weather_alert_active(chat_id, False)
            await query.answer("🔕 បានបិទដំណឹងអាកាសធាតុ ៥:០០ ព្រឹក!", show_alert=True)
            await query.edit_message_reply_markup(reply_markup=get_main_menu_keyboard(chat_id))
            
        elif data == "btn_test_weather":
            await query.answer("កំពុងទាញយកគំរូដំណឹង 5AM...")
            w_settings = get_user_weather_settings(chat_id)
            lat = w_settings.get("latitude", DEFAULT_LAT)
            lon = w_settings.get("longitude", DEFAULT_LON)
            loc_name = w_settings.get("location_name", DEFAULT_LOCATION_NAME)
            
            w_data = await fetch_weather(lat, lon)
            if w_data:
                msg = (
                    "🧪 *[សារតេស្តសាកល្បង - 5:00 AM Weather Alert]*\n\n"
                    + format_weather_message(w_data, loc_name, is_daily_alert=True)
                )
            else:
                msg = "❌ មិនអាចទាញយកព័ត៌មានអាកាសធាតុបានទេ។"
                
            await query.edit_message_text(
                msg,
                reply_markup=get_back_keyboard(),
                parse_mode="Markdown"
            )

        elif data == "btn_status":
            await query.answer()
            subscribed = is_subscribed(chat_id)
            today_holiday = get_today_holiday()
            today_date = get_current_cambodia_date()
            w_settings = get_user_weather_settings(chat_id)
            loc_name = w_settings.get("location_name", "ភ្នំពេញ")
            weather_active = w_settings.get("is_active", True)
            
            status_text = (
                "📊 *ស្ថានភាពគណនីរបស់អ្នក (Account Status)*\n\n"
                f"👤 ឈ្មោះ: *{user.full_name}*\n"
                f"🆔 Telegram ID: `{chat_id}`\n"
                f"📅 កាលបរិច្ឆេទថ្ងៃនេះ: `{today_date}` (Asia/Phnom_Penh)\n"
                f"📍 ទីតាំងអាកាសធាតុ: *{loc_name}*\n"
                f"🌅 ដំណឹងអាកាសធាតុ ៥:០០ ព្រឹក: {'✅ កំពុងបើក (Active)' if weather_active else '❌ បានបិទ (Inactive)'}\n"
                f"🔔 ដំណឹងបុណ្យជាតិ ៤:០០ ព្រឹក: {'✅ កំពុងបើក (Active)' if subscribed else '❌ បានបិទ (Inactive)'}\n"
                f"🎉 ថ្ងៃឈប់សម្រាកថ្ងៃនេះ: {today_holiday['name_km'] if today_holiday else 'ពុំមែនជាថ្ងៃឈប់សម្រាកទេ'}\n"
            )
            await query.edit_message_text(
                status_text,
                reply_markup=get_back_keyboard(),
                parse_mode="Markdown"
            )
            
        elif data == "btn_subscribe":
            add_subscriber(chat_id, user.username, query.message.chat.type)
            await query.answer("✅ បានបើកការដាស់តឿនបុណ្យជាតិ ៤:០០ ព្រឹកជោគជ័យ!", show_alert=True)
            await query.edit_message_reply_markup(reply_markup=get_main_menu_keyboard(chat_id))
            
        elif data == "btn_unsubscribe":
            remove_subscriber(chat_id)
            await query.answer("🔕 បានបិទការដាស់តឿនបុណ្យជាតិ ៤:០០ ព្រឹក!", show_alert=True)
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
                "🌤️ *២. ដំណឹងអាកាសធាតុ ៥:០០ ព្រឹក:*\n"
                "• ផ្ញើរបាយការណ៍អាកាសធាតុប្រចាំថ្ងៃនៅទីតាំងរបស់អ្នករាល់ព្រឹក\n"
                "• គាំទ្រការកំណត់តាម GPS ឬជ្រើសរើសរាជធានី-ខេត្ត\n\n"
                "🗓️ *៣. ប្រតិទិនបុណ្យជាតិ (Cambodia Holidays):*\n"
                "• រួមបញ្ចូលថ្ងៃឈប់សម្រាកផ្លូវការទាំងអស់នៅកម្ពុជា\n"
                "• ជូនដំណឹងស្វ័យប្រវត្តិនាពេលទៀបភ្លឺ ម៉ោង ៤:០០ ព្រឹក\n\n"
                "✨ *៤. បញ្ជា Command រហ័ស:*\n"
                "• `/start` - បើកផ្ទាំង Dashboard មេ\n"
                "• `/weather` - មើលអាកាសធាតុបច្ចុប្បន្ន\n"
                "• `/location` - កំណត់ទីតាំងអាកាសធាតុ\n"
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
