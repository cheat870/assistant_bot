import re
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton,
)
from telegram.ext import ContextTypes

from config import BOT_TIMEZONE, WEATHER_ALERT_HOUR, ALERT_HOUR, ADMIN_USER_ID
from database import (
    add_subscriber,
    remove_subscriber,
    is_subscribed,
    get_user_weather_settings,
    set_user_location,
    set_weather_alert_active,
    add_reminder,
    get_user_reminders,
    delete_reminder,
    is_ai_mode,
    set_ai_mode,
    clear_chat_history,
    get_all_registered_chats,
    is_antispam_enabled,
    set_antispam_enabled,
    clear_user_expenses,
    is_welcome_enabled,
    set_welcome_enabled,
    save_pdf_session,
    get_pdf_session,
    clear_pdf_session,
)
from services.holiday_calendar import (
    format_upcoming_message,
    format_calendar_message,
    format_alert_message,
    get_today_holiday,
    get_upcoming_holidays,
    get_current_cambodia_date,
)
from services.weather_service import (
    fetch_weather,
    format_weather_message,
    reverse_geocode_async,
    get_detailed_cambodia_location,
    format_detailed_location_message,
    DEFAULT_LAT,
    DEFAULT_LON,
    DEFAULT_LOCATION_NAME,
)
from services.ai_service import (
    query_ai,
    query_continuous_ai,
    process_voice_ai,
    process_vision_ai,
)
from services.finance_service import format_finance_report, convert_currency_text
from services.tools_service import generate_qr_code, read_qr_code
from services.expense_service import (
    parse_expense_text,
    record_transaction,
    format_record_success,
    format_budget_report,
)
from services.tts_service import generate_tts_audio
from services.linguistics_service import check_khmer_spelling, translate_pro
from services.music_service import download_song, identify_tiktok_sound
from services.image_service import remove_background
from services.news_service import generate_morning_news_digest
from services.pdf_service import analyze_and_summarize_pdf, answer_pdf_question
from services.image_enhancer_service import enhance_image
from services.watermark_service import apply_watermark
from services.welcome_banner_service import generate_welcome_banner
from services.image_location_service import (
    extract_gps_from_image_bytes,
    format_photo_gps_message,
    identify_location_via_vision,
)

logger = logging.getLogger(__name__)

# Preset Cambodian Provinces
PROVINCE_PRESETS = {
    "phnompenh": {"name": "រាជធានីភ្នំពេញ", "lat": 11.5564, "lon": 104.9282},
    "siemreap": {"name": "ខេត្តសៀមរាប", "lat": 13.3671, "lon": 103.8448},
    "battambang": {"name": "ខេត្តបាត់ដំបង", "lat": 13.0957, "lon": 103.2022},
    "sihanoukville": {"name": "ខេត្តព្រះសីហនុ", "lat": 10.6275, "lon": 103.5221},
    "kampot": {"name": "ខេត្តកំពត", "lat": 10.6104, "lon": 104.1815},
    "kandal": {"name": "ខេត្តកណ្ដាល", "lat": 11.4588, "lon": 104.9458},
}

def parse_reminder_input(text: str):
    """Parse relative time (e.g. 15m, 2h) or absolute time (e.g. 08:30, 8:30pm)."""
    text = text.strip()
    now = datetime.now(BOT_TIMEZONE)
    
    # Match relative (e.g., 15m, 30min, 2h, 1hour)
    match_rel = re.match(r"^(\d+)\s*(m|min|minute|minutes|h|hour|hours?|នាទី|ម៉ោង)\s+(.+)$", text, re.IGNORECASE)
    if match_rel:
        qty = int(match_rel.group(1))
        unit = match_rel.group(2).lower()
        msg = match_rel.group(3).strip()
        delta = timedelta(hours=qty) if ("h" in unit or "ម៉ោង" in unit) else timedelta(minutes=qty)
        target = now + delta
        return target.astimezone(pytz_utc).isoformat(), target.strftime("%H:%M (%d/%m)"), msg
        
    # Match clock time (e.g., 08:30, 14:00, 8:30pm)
    match_clock = re.match(r"^(\d{1,2})[:\.](\d{2})\s*(am|pm)?\s+(.+)$", text, re.IGNORECASE)
    if match_clock:
        hr = int(match_clock.group(1))
        mn = int(match_clock.group(2))
        ampm = match_clock.group(3)
        msg = match_clock.group(4).strip()
        if ampm:
            ampm = ampm.lower()
            if ampm == "pm" and hr < 12:
                hr += 12
            elif ampm == "am" and hr == 12:
                hr = 0
        target = now.replace(hour=hr, minute=mn, second=0, microsecond=0)
        if target <= now:
            target += timedelta(days=1)
        return target.astimezone(pytz_utc).isoformat(), target.strftime("%H:%M (%d/%m)"), msg
        
    return None

import pytz
pytz_utc = pytz.utc

def get_welcome_text(user_first_name: str) -> str:
    """Standard welcome message text for the dashboard."""
    return (
        f"🌟 *មជ្ឈមណ្ឌលជំនួយការឆ្លាតវៃ (Smart Assistant Hub)* 🇰🇭\n\n"
        f"👋 សួស្តី *{user_first_name}*! សូមជ្រើសរើសមុខងារដែលអ្នកត្រូវការប្រើប្រាស់៖\n\n"
        "📥 *១. Video Downloader:* Copy link (TikTok, YouTube, Facebook, IG, X) ផ្ញើចូលទីនេះភ្លាមៗ\n"
        "🎧 *២. ចម្រៀង MP3:* វាយ `/song <ឈ្មោះបទ>` ទាញយក file MP3 320kbps ភ្លាមៗ\n"
        "📊 *៣. កត់ត្រាចំណូល-ចំណាយ:* វាយ `/spend 5$ coffee` ឬ `ចាយ 20,000៛ ញ៉ាំបាយ` មើលរបាយការណ៍ `/budget`\n"
        "🗣️ *៤. អានជាសំឡេង (TTS):* វាយ `/speak <អត្ថបទ>` បម្លែងអក្សរទៅជាសំឡេងនិយាយភាសាខ្មែរ/អង់គ្លេស\n"
        "✍️ *៥. ពិនិត្យអក្ខរាវិរុទ្ធខ្មែរ:* វាយ `/check <អត្ថបទ>` កែតម្រូវតាមវចនានុក្រម សម្តេច ជួន ណាត\n"
        "🌐 *៦. បកប្រែភាសា Pro:* វាយ `/translate <អត្ថបទ>` បកប្រែ English ⬄ Khmer ជាមួយការបញ្ចេញសំឡេង\n"
        "✂️ *៧. កាត់ Background រូបភាព:* ផ្ញើរូបភាព ឬ Reply ដោយវាយ `/rembg` ក្លាយជា Transparent PNG\n"
        "💰 *៨. សេដ្ឋកិច្ចកម្ពុជា:* អត្រាប្តូរប្រាក់ NBC/USD/KHR, តម្លៃមាស, តម្លៃប្រេងឥន្ធនៈ (`/finance`)\n"
        "📰 *៩. ព័ត៌មានពេលព្រឹក ៧:០០ AM:* សេចក្តីសង្ខេបព័ត៌មានជាតិ & បច្ចេកវិទ្យា (`/news`)\n"
        "🛡️ *១០. ការពារ Group Telegram:* ទប់ស្កាត់ Spam, Casino Ads & Bot ក្លែងក្លាយ (`/antispam`)\n"
        "🔔 *១១. សារដាស់តឿន & អាកាសធាតុ:* `/remind` និងដំណឹងអាកាសធាតុ ៥:០០ ព្រឹកស្វ័យប្រវត្ត\n"
        "📄 *១២. Chat with PDF:* ផ្ញើ File PDF មកកាន់ Bot នឹងអាន & សង្ខេបចំណុចសំខាន់ៗភ្លាមៗ (`/pdf`)\n"
        "🔍 *១៣. ធ្វើឱ្យច្បាស់ HD:* វាយ `/enhance` លើរូបភាពដើម្បីសម្អាត Noise & Super-Resolution\n"
        "💧 *១៤. ដាក់ Watermark:* វាយ `/watermark <ឈ្មោះហាង>` បោះត្រាការពាររូបភាពទំនិញ\n"
        "🖼️ *១៥. Banner ស្វាគមន៍:* បង្កើតរូបភាពស្វាគមន៍សមាជិកថ្មីក្នុង Group ស្វ័យប្រវត្ត (`/welcome on|off`)\n\n"
        "👇 _សូមចុចជ្រើសរើស Menu ខាងក្រោម៖_"
    )

def get_main_menu_keyboard(chat_id: int) -> InlineKeyboardMarkup:
    """Upgraded inline dashboard keyboard with all modern features."""
    holiday_sub = is_subscribed(chat_id)
    holiday_btn_text = "🔕 បិទបុណ្យជាតិ 4AM" if holiday_sub else "🔔 បើកបុណ្យជាតិ 4AM"
    holiday_callback = "btn_unsubscribe" if holiday_sub else "btn_subscribe"
    
    w_settings = get_user_weather_settings(chat_id)
    weather_active = w_settings.get("is_active", True)
    weather_btn_text = "🔕 បិទអាកាសធាតុ 5AM" if weather_active else "🌅 បើកអាកាសធាតុ 5AM"
    weather_callback = "btn_toggle_weather_off" if weather_active else "btn_toggle_weather_on"
    
    ai_active = is_ai_mode(chat_id)
    ai_btn_text = "💬 បិទ AI Continuous Chat" if ai_active else "🤖 បើក AI Continuous Chat"
    
    keyboard = [
        [
            InlineKeyboardButton("📥 របៀបទាញយកវីដេអូ", callback_data="btn_video_help"),
            InlineKeyboardButton("🎧 ស្វែងរកចម្រៀង MP3", callback_data="btn_music_help"),
        ],
        [
            InlineKeyboardButton("📊 ចំណូល-ចំណាយ (Budget)", callback_data="btn_budget"),
            InlineKeyboardButton("💰 សេដ្ឋកិច្ច / មាស / សាំង", callback_data="btn_finance"),
        ],
        [
            InlineKeyboardButton("📰 ព័ត៌មានពេលព្រឹក 7AM", callback_data="btn_news"),
            InlineKeyboardButton("🌤️ អាកាសធាតុបច្ចុប្បន្ន", callback_data="btn_weather_now"),
        ],
        [
            InlineKeyboardButton(holiday_btn_text, callback_data=holiday_callback),
            InlineKeyboardButton(weather_btn_text, callback_data=weather_callback),
        ],
        [
            InlineKeyboardButton(ai_btn_text, callback_data="btn_toggle_aimode"),
            InlineKeyboardButton("⏰ សារដាស់តឿន (Reminders)", callback_data="btn_reminders"),
        ],
        [
            InlineKeyboardButton("📄 Chat with PDF (/pdf)", callback_data="btn_pdf_help"),
            InlineKeyboardButton("🔍 ធ្វើឱ្យច្បាស់ HD (/enhance)", callback_data="btn_photo_enhance_help"),
        ],
        [
            InlineKeyboardButton("🛠️ ឧបករណ៍ QR / KHQR", callback_data="btn_tools_menu"),
            InlineKeyboardButton("🧹 សម្អាតសារចាស់ៗ (/clean)", callback_data="btn_clean_chat"),
        ],
        [
            InlineKeyboardButton("✨ ជំនួយការ AI (Gemini)", callback_data="btn_ai_menu"),
            InlineKeyboardButton("💡 ការណែនាំ (Help)", callback_data="btn_help"),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_persistent_bottom_keyboard() -> ReplyKeyboardMarkup:
    """Persistent reply keyboard displayed at the bottom of the chat."""
    keyboard = [
        [KeyboardButton("📊 ចំណូល-ចំណាយ"), KeyboardButton("💰 សេដ្ឋកិច្ច/មាស/សាំង")],
        [KeyboardButton("🌤️ អាកាសធាតុ"), KeyboardButton("📰 ព័ត៌មានពេលព្រឹក")],
        [KeyboardButton("📍 ផ្ញើទីតាំង GPS", request_location=True), KeyboardButton("⏰ Reminders")],
        [KeyboardButton("✨ AI Chat"), KeyboardButton("🧹 សម្អាតសារ"), KeyboardButton("🏠 ផ្ទាំង Menu មេ")]
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

# -------------------------------------------------------------
# Core Single-Message Manager ("បង្ហាញសារថ្មី លុបសារចាស់")
# -------------------------------------------------------------
async def send_clean_response(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
    reply_markup=None,
    parse_mode="Markdown",
    delete_user_message: bool = True
):
    """
    Core Single-Message Manager ('បង្ហាញសារថ្មី លុបសារចាស់'):
    1. In private chats, deletes user's trigger message so commands/buttons don't linger.
    2. Deletes previous active bot message/menu tracked in user_data.
    3. Safely sends the new message (with markdown entity error fallback).
    4. Records the new message ID in context.user_data['last_bot_msg_id'] and ['last_menu_id'].
    """
    chat = update.effective_chat if update else None
    if not chat:
        return None
    chat_id = chat.id
    user_msg = update.message if update else None

    # 1. Delete user message in private chat to keep chat clean
    if delete_user_message and user_msg and chat.type == "private":
        try:
            await user_msg.delete()
        except Exception:
            pass

    # 2. Delete previous bot message/menu if tracked
    prev_id = context.user_data.get("last_bot_msg_id") or context.user_data.get("last_menu_id")
    if prev_id:
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=prev_id)
        except Exception:
            pass

    # 3. Send new message safely
    try:
        sent = await context.bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=reply_markup,
            parse_mode=parse_mode
        )
    except Exception as e:
        err_str = str(e).lower()
        if "parse entities" in err_str or "entity" in err_str:
            sent = await context.bot.send_message(
                chat_id=chat_id,
                text=text,
                reply_markup=reply_markup,
                parse_mode=None
            )
        else:
            raise

    # 4. Update tracking
    context.user_data["last_bot_msg_id"] = sent.message_id
    context.user_data["last_menu_id"] = sent.message_id
    return sent

# -------------------------------------------------------------
# Command Handlers
# -------------------------------------------------------------
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command with 'បង្ហាញសារថ្មី លុបសារចាស់' clean interface."""
    chat = update.effective_chat
    user = update.effective_user
    
    add_subscriber(chat.id, user.username if user else None, chat.type)
    
    first_name = user.first_name if user else "មិត្តសំឡាញ់"
    await send_clean_response(
        update=update,
        context=context,
        text=get_welcome_text(first_name),
        reply_markup=get_main_menu_keyboard(chat.id),
        parse_mode="Markdown"
    )

async def finance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /finance command to view exchange rates, gold, and fuel prices."""
    await update.message.chat.send_action("typing")
    report = await format_finance_report()
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔄 ធ្វើបច្ចុប្បន្នភាព", callback_data="btn_finance"),
            InlineKeyboardButton("🔙 Menu ដើម", callback_data="btn_back_main")
        ]
    ])
    await send_clean_response(update, context, report, reply_markup=keyboard)

async def convert_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /convert <amount> <from> <to> command."""
    args = context.args or []
    if len(args) < 3:
        help_msg = (
            "💱 *របៀបប្រើប្រាស់ការប្តូររូបិយប័ណ្ណ៖*\n\n"
            "សូមវាយ៖ `/convert <ចំនួនទឹកប្រាក់> <ពី> <ទៅ>`\n\n"
            "• ឧទាហរណ៍៖ `/convert 100 USD KHR`\n"
            "• ឧទាហរណ៍៖ `/convert 400000 KHR USD`\n"
            "• ឧទាហរណ៍៖ `/convert 1000 THB KHR`"
        )
        await send_clean_response(update, context, help_msg, reply_markup=get_back_keyboard())
        return
        
    try:
        amount = float(args[0].replace(",", ""))
        from_c = args[1]
        to_c = args[2]
        res = await convert_currency_text(amount, from_c, to_c)
        await send_clean_response(update, context, res, reply_markup=get_back_keyboard())
    except ValueError:
        await send_clean_response(update, context, "❌ ចំនួនទឹកប្រាក់មិនត្រឹមត្រូវ។ សូមបញ្ចូលលេខជាក់ស្តែង ឧ. `/convert 50 USD KHR`", reply_markup=get_back_keyboard())

async def remind_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /remind <time> <message> command with auto-cleanup of old confirmation messages."""
    chat = update.effective_chat
    chat_id = chat.id
    text = " ".join(context.args) if context.args else ""

    # In private chat, delete user's command message to keep the chat tidy
    if chat.type == "private":
        try:
            await update.message.delete()
        except Exception:
            pass

    # Clean up previous reminder confirmation/help message if one exists
    prev_remind_id = context.user_data.get("last_remind_msg_id")
    if prev_remind_id:
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=prev_remind_id)
        except Exception:
            pass

    if not text:
        sent = await context.bot.send_message(
            chat_id=chat_id,
            text=(
                "⏰ *របៀបកំណត់សារដាស់តឿន (Custom Reminders)៖*\n\n"
                "សូមវាយ៖ `/remind <ម៉ោង> <កិច្ចការដែលត្រូវធ្វើ>`\n\n"
                "👉 *ឧទាហរណ៍ម៉ោងជាក់លាក់៖*\n"
                "• `/remind 08:30 ត្រូវទៅជួបភ្ញៀវនៅហាងកាហ្វេ`\n"
                "• `/remind 21:00 លេបថ្នាំ និងចូលគេង`\n\n"
                "👉 *ឧទាហរណ៍កំណត់តាមនាទី/ម៉ោងបន្ទាប់៖*\n"
                "• `/remind 15m ឆុងកាហ្វេ និងពិនិត្យ Email`\n"
                "• `/remind 2h បញ្ចប់របាយការណ៍ការងារ`"
            ),
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("📋 បញ្ជី Reminders", callback_data="btn_reminders"),
                    InlineKeyboardButton("🧹 សម្អាតសារ", callback_data="btn_clean_chat")
                ],
                [InlineKeyboardButton("🔙 Menu ដើម", callback_data="btn_back_main")]
            ]),
            parse_mode="Markdown"
        )
        context.user_data["last_remind_msg_id"] = sent.message_id
        return
        
    parsed = parse_reminder_input(text)
    if not parsed:
        sent = await context.bot.send_message(
            chat_id=chat_id,
            text=(
                "❌ *ទម្រង់ម៉ោងមិនត្រឹមត្រូវ!*\n\n"
                "សូមបញ្ជាក់ម៉ោងដូចជា៖ `08:30`, `14:00`, `15m`, ឬ `2h` រួមជាមួយអត្ថបទកិច្ចការ។"
            ),
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🧹 សម្អាតសារ", callback_data="btn_clean_chat")],
                [InlineKeyboardButton("🔙 Menu ដើម", callback_data="btn_back_main")]
            ]),
            parse_mode="Markdown"
        )
        context.user_data["last_remind_msg_id"] = sent.message_id
        return
        
    remind_at, time_str, message_body = parsed
    rem_id = add_reminder(chat_id, remind_at, time_str, message_body)

    # Fetch active reminders to display a compact consolidated summary
    active_rems = get_user_reminders(chat_id)
    active_summary = ""
    if active_rems and len(active_rems) > 1:
        active_lines = [f"• 🕒 `{r['time_str']}`: {r['message'][:28]}" for r in active_rems[-4:]]
        active_summary = f"\n\n📋 *សារដាស់តឿនសកម្មទាំងអស់ ({len(active_rems)})៖*\n" + "\n".join(active_lines)

    sent = await context.bot.send_message(
        chat_id=chat_id,
        text=(
            f"✅ *បានកត់ត្រាសារដាស់តឿនជោគជ័យ!* ⏰\n\n"
            f"🕒 *ម៉ោងរំលឹក៖* `{time_str}` (ម៉ោងនៅកម្ពុជា)\n"
            f"📝 *កិច្ចការ៖* {message_body}\n\n"
            f"🔔 Bot នឹងផ្ញើសាររំលឹកអ្នកចំពេលនេះដោយស្វ័យប្រវត្ត!"
            f"{active_summary}"
        ),
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton("📋 បញ្ជី Reminders", callback_data="btn_reminders"),
                InlineKeyboardButton("🧹 សម្អាតសារ", callback_data="btn_clean_chat")
            ],
            [InlineKeyboardButton("🔙 Menu ដើម", callback_data="btn_back_main")]
        ]),
        parse_mode="Markdown"
    )
    context.user_data["last_remind_msg_id"] = sent.message_id

async def reminders_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /reminders command to list user's reminders with auto-cleanup."""
    chat = update.effective_chat
    chat_id = chat.id

    if chat.type == "private":
        try:
            await update.message.delete()
        except Exception:
            pass

    # Clean up previous reminder card so duplicate lists don't stack up
    prev_remind_id = context.user_data.get("last_remind_msg_id")
    if prev_remind_id:
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=prev_remind_id)
        except Exception:
            pass

    rems = get_user_reminders(chat_id)
    if not rems:
        sent = await context.bot.send_message(
            chat_id=chat_id,
            text=(
                "⏰ *អ្នកពុំទាន់មានសារដាស់តឿននៅឡើយទេ។*\n\n"
                "ដើម្បីកំណត់ដាស់តឿន សូមវាយ៖\n`/remind <ម៉ោង> <កិច្ចការ>` ឧទាហរណ៍ `/remind 08:30 ជួបភ្ញៀវ`"
            ),
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("🧹 សម្អាតសារ", callback_data="btn_clean_chat"),
                    InlineKeyboardButton("🔙 Menu ដើម", callback_data="btn_back_main")
                ]
            ]),
            parse_mode="Markdown"
        )
        context.user_data["last_remind_msg_id"] = sent.message_id
        return
        
    lines = ["⏰ *បញ្ជីសារដាស់តឿនរបស់អ្នក (Active Reminders)៖*\n"]
    buttons = []
    for r in rems:
        lines.append(f"• 🕒 *`{r['time_str']}`*: {r['message']}")
        buttons.append([InlineKeyboardButton(f"❌ លុប: {r['message'][:20]}", callback_data=f"delrem_{r['id']}")])
        
    buttons.append([
        InlineKeyboardButton("🧹 សម្អាតសារ", callback_data="btn_clean_chat"),
        InlineKeyboardButton("🔙 Menu ដើម", callback_data="btn_back_main")
    ])
    sent = await context.bot.send_message(
        chat_id=chat_id,
        text="\n".join(lines),
        reply_markup=InlineKeyboardMarkup(buttons),
        parse_mode="Markdown"
    )
    context.user_data["last_remind_msg_id"] = sent.message_id

async def clean_chat_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle /clean or /clear [count] to wipe out old messages and reset chat to a clean state.
    Default count: 40 messages, maximum 100.
    Deletes old status updates, menus, and user command clutter.
    """
    chat = update.effective_chat
    user = update.effective_user
    current_msg = update.message
    current_msg_id = current_msg.message_id if current_msg else None

    count = 40
    if context.args:
        try:
            count = min(max(int(context.args[0]), 5), 100)
        except ValueError:
            count = 40

    # Delete the /clean command message itself first if in private chat
    if current_msg and chat.type == "private":
        try:
            await current_msg.delete()
        except Exception:
            pass

    deleted_count = 0
    if current_msg_id:
        start_id = max(1, current_msg_id - count)
        msg_ids = list(range(start_id, current_msg_id))
        
        # Batch delete via delete_messages
        try:
            for i in range(0, len(msg_ids), 100):
                chunk = msg_ids[i:i+100]
                await context.bot.delete_messages(chat_id=chat.id, message_ids=chunk)
                deleted_count += len(chunk)
        except Exception:
            # Fallback to individual deletion
            for mid in reversed(msg_ids):
                try:
                    await context.bot.delete_message(chat_id=chat.id, message_id=mid)
                    deleted_count += 1
                except Exception:
                    pass

    # Clear stored tracking IDs in user_data
    context.user_data.pop("last_remind_msg_id", None)
    context.user_data.pop("last_menu_id", None)

    clean_notice = (
        f"🧹 *បានសម្អាតសារចាស់ៗដោយជោគជ័យ!* ✨\n\n"
        f"ឥឡូវនេះការជជែករបស់អ្នកមានសភាពស្អាតបាត និងគ្មានសារចាស់ៗកកកុញទៀតឡើយ។\n"
        f"សូមជ្រើសរើសមុខងារដែលចង់ប្រើប្រាស់បន្តខាងក្រោម៖"
    )
    sent_menu = await context.bot.send_message(
        chat_id=chat.id,
        text=clean_notice,
        reply_markup=get_main_menu_keyboard(chat.id),
        parse_mode="Markdown"
    )
    context.user_data["last_menu_id"] = sent_menu.message_id

async def aimode_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /aimode command to toggle continuous AI chat mode."""
    chat_id = update.effective_chat.id
    current = is_ai_mode(chat_id)
    new_state = not current
    set_ai_mode(chat_id, new_state)
    
    if new_state:
        msg = (
            "🤖 *បានបើកដំណើរការ AI Continuous Chat Mode!* ✨\n\n"
            "💬 ឥឡូវនេះ លោកអ្នកអាចវាយសារជជែកលេង ឬសួរសំណួរបានដោយសេរី ដូច ChatGPT ពិតៗ **ដោយមិនបាច់វាយ `/ask` នាំមុខឡើយ!**\n"
            "Bot នឹងចងចាំការជជែកឆ្លើយឆ្លងជាបន្តបន្ទាប់។\n\n"
            "👉 _ដើម្បីបិទវិញ សូមវាយ `/aimode` ម្តងទៀត ឬចុចប៊ូតុងខាងក្រោម៖_"
        )
    else:
        msg = (
            "🔕 *បានបិទ AI Continuous Chat Mode រួចរាល់ហើយ។*\n\n"
            "លោកអ្នកអាចសួរ AI ដោយវាយ `/ask <សំណួរ>` ដូចធម្មតា។"
        )
        
    await send_clean_response(
        update, context,
        msg,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("💬 បើក/បិទ AI Mode", callback_data="btn_toggle_aimode")],
            [InlineKeyboardButton("🔙 Menu ដើម", callback_data="btn_back_main")]
        ]),
        parse_mode="Markdown"
    )

async def qr_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /qr <text/url> command."""
    text = " ".join(context.args) if context.args else ""
    if not text:
        await update.message.reply_text(
            "🔲 *របៀបបង្កើត QR Code៖*\n\n"
            "សូមវាយ៖ `/qr <អត្ថបទ ឬ Link>`\n\n"
            "• ឧទាហរណ៍៖ `/qr https://t.me/Researchmap_bot`\n"
            "• ឧទាហរណ៍៖ `/qr 012345678`\n\n"
            "💡 _ដើម្បីអាន QR Code ឬ KHQR គ្រាន់តែផ្ញើរូបភាព QR Code នោះចូលក្នុង Bot នេះភ្លាមៗ!_",
            parse_mode="Markdown"
        )
        return
        
    await update.message.chat.send_action("upload_photo")
    try:
        bio = generate_qr_code(text)
        caption = f"🔲 *QR Code របស់អ្នកត្រូវបានបង្កើតជោគជ័យ!* ✨\n\n📝 ទិន្នន័យ៖ `{text[:100]}`"
        try:
            await update.message.reply_photo(
                photo=bio,
                caption=caption,
                parse_mode="Markdown"
            )
        except Exception:
            bio.seek(0)
            await update.message.reply_photo(
                photo=bio,
                caption=f"🔲 QR Code របស់អ្នកត្រូវបានបង្កើតជោគជ័យ!\n\n📝 ទិន្នន័យ៖ {text[:100]}"
            )
    except Exception as e:
        logger.error(f"Error generating QR: {e}")
        await update.message.reply_text("❌ មិនអាចបង្កើត QR Code បានទេ។")

async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /broadcast <message> (Admin Only)."""
    user = update.effective_user
    if not user or user.id != ADMIN_USER_ID:
        await update.message.reply_text("⛔ អ្នកមិនមានសិទ្ធិប្រើប្រាស់ Command នេះទេ (Admin Only)!")
        return
        
    broadcast_msg = " ".join(context.args) if context.args else ""
    if not broadcast_msg:
        await update.message.reply_text(
            "📢 *របៀបប្រកាសដំណឹង (Admin Broadcast)៖*\n\n"
            "សូមវាយ៖ `/broadcast <ខ្លឹមសារដំណឹង>`\n\n"
            "សារនេះនឹងត្រូវផ្ញើទៅកាន់ Users និង Groups ទាំងអស់ដែលធ្លាប់បានប្រើ Bot!",
            parse_mode="Markdown"
        )
        return
        
    chats = get_all_registered_chats()
    if not chats:
        await update.message.reply_text("❌ ពុំទាន់មាន User ឬ Group ណាមួយនៅក្នុង Database ឡើយ។")
        return
        
    status_msg = await update.message.reply_text(f"⏳ កំពុងផ្ញើសារប្រកាសដំណឹងទៅកាន់ {len(chats)} chats...")
    
    formatted_msg = (
        f"📢 *[សេចក្ដីប្រកាសដំណឹងផ្លូវការ / Announcement]* 🇰🇭\n\n"
        f"{broadcast_msg}\n\n"
        f"✨ _ផ្ញើដោយអ្នកគ្រប់គ្រងប្រព័ន្ធ (Admin)_"
    )
    
    success_count = 0
    for cid in chats:
        try:
            await context.bot.send_message(
                chat_id=cid,
                text=formatted_msg,
                parse_mode="Markdown"
            )
            success_count += 1
            await asyncio.sleep(0.05)
        except Exception as e:
            logger.debug(f"Failed broadcast to {cid}: {e}")
            
    await status_msg.edit_text(
        f"✅ *ការប្រកាសដំណឹងបានបញ្ចប់!* 📊\n\n"
        f"• ផ្ញើបានជោគជ័យ៖ *{success_count}* / *{len(chats)}* chats\n"
        f"• បរាជ័យ៖ *{len(chats) - success_count}* (អាចបិទ Bot)",
        parse_mode="Markdown"
    )

# -------------------------------------------------------------
# Personal Expense & Income Tracker Handlers
# -------------------------------------------------------------
async def spend_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Record an expense: /spend 5$ coffee or /spend 20000r lunch."""
    raw = " ".join(context.args) if context.args else ""
    if not raw:
        await update.message.reply_text(
            "💸 *របៀបកត់ត្រាចំណាយ (Expense Tracker)៖*\n\n"
            "សូមវាយ៖ `/spend <ចំនួនទឹកប្រាក់> <ចំណាំ>`\n\n"
            "• ឧទាហរណ៍៖ `/spend 5$ coffee`\n"
            "• ឧទាហរណ៍៖ `/spend 20,000៛ ញ៉ាំបាយ`\n"
            "• ឧទាហរណ៍៖ `/spend 15 USD សាំងឡាន`\n\n"
            "💡 _អ្នកក៏អាចវាយជាភាសាខ្មែរធម្មតាបានដែរ ដូចជា:_ `ចាយ 20,000៛ ញ៉ាំបាយ`",
            parse_mode="Markdown"
        )
        return
        
    parsed = parse_expense_text(raw, force_type="expense")
    if not parsed:
        await update.message.reply_text(
            "⚠️ មិនអាចស្គាល់ចំនួនទឹកប្រាក់បានឡើយ។ សូមបញ្ជាក់ដូចជា `/spend 5$ coffee` ឬ `/spend 20,000៛ បាយ`។"
        )
        return
        
    record_transaction(update.effective_chat.id, parsed)
    msg = format_record_success(parsed)
    await safe_reply_text(update.message, msg)

async def income_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Record an income: /income 500$ monthly salary."""
    raw = " ".join(context.args) if context.args else ""
    if not raw:
        await update.message.reply_text(
            "💰 *របៀបកត់ត្រាចំណូល (Income Tracker)៖*\n\n"
            "សូមវាយ៖ `/income <ចំនួនទឹកប្រាក់> <ចំណាំ>`\n\n"
            "• ឧទាហរណ៍៖ `/income 500$ ប្រាក់ខែ`\n"
            "• ឧទាហរណ៍៖ `/income 200$ លក់ទំនិញ`\n\n"
            "💡 _អ្នកក៏អាចវាយជាភាសាខ្មែរធម្មតាបានដែរ ដូចជា:_ `ចំណូល 50$ រកស៊ី`",
            parse_mode="Markdown"
        )
        return
        
    parsed = parse_expense_text(raw, force_type="income")
    if not parsed:
        await update.message.reply_text(
            "⚠️ មិនអាចស្គាល់ចំនួនទឹកប្រាក់បានឡើយ។ សូមបញ្ជាក់ដូចជា `/income 500$ salary`។"
        )
        return
        
    record_transaction(update.effective_chat.id, parsed)
    msg = format_record_success(parsed)
    await safe_reply_text(update.message, msg)

async def budget_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """View comprehensive budget & expense report with 'បង្ហាញសារថ្មី លុបសារចាស់': /budget."""
    report = format_budget_report(update.effective_chat.id, days=30)
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔄 ធ្វើបច្ចុប្បន្នភាព", callback_data="btn_budget"),
            InlineKeyboardButton("🗑️ សម្អាតប្រវត្តិ", callback_data="btn_clear_expenses_ask")
        ],
        [InlineKeyboardButton("🔙 Menu ដើម", callback_data="btn_back_main")]
    ])
    await send_clean_response(update, context, report, reply_markup=keyboard)

async def clear_expenses_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Clear all expense records for this chat: /clear_expenses."""
    chat_id = update.effective_chat.id
    count = clear_user_expenses(chat_id)
    await send_clean_response(
        update, context,
        f"✅ បានលុបកំណត់ត្រាចំណូល-ចំណាយចំនួន {count} ជោគជ័យ!",
        reply_markup=get_back_keyboard()
    )

# -------------------------------------------------------------
# Text-to-Speech (TTS) & Audio Speech Handler
# -------------------------------------------------------------
async def speak_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generate audio voice note from text: /speak <text>."""
    text = " ".join(context.args) if context.args else ""
    if not text and update.message.reply_to_message and update.message.reply_to_message.text:
        text = update.message.reply_to_message.text
        
    if not text:
        await update.message.reply_text(
            "🗣️ *របៀបប្រើប្រាស់ Text-to-Speech (សំឡេងខ្មែរ/អង់គ្លេស)៖*\n\n"
            "សូមវាយ៖ `/speak <អត្ថបទ>`\n"
            "ឬ Reply លើសារណាមួយរួចវាយ `/speak`\n\n"
            "• ឧទាហរណ៍៖ `/speak សួស្តីបងប្អូនទាំងអស់គ្នា!`",
            parse_mode="Markdown"
        )
        return
        
    await update.message.chat.send_action("record_voice")
    try:
        audio_fp = generate_tts_audio(text)
        await update.message.reply_voice(
            voice=audio_fp,
            caption=f"🗣️ *សំឡេងអាន៖* _{text[:50]}..._",
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Error generating TTS: {e}")
        await update.message.reply_text(f"❌ មិនអាចបម្លែងជាសំឡេងបានទេ៖ {str(e)[:100]}")

# -------------------------------------------------------------
# Khmer Spellchecker & Grammar Handler
# -------------------------------------------------------------
async def check_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Khmer spellcheck & grammar review: /check <text>."""
    text = " ".join(context.args) if context.args else ""
    if not text and update.message.reply_to_message and update.message.reply_to_message.text:
        text = update.message.reply_to_message.text

    if not text:
        await update.message.reply_text(
            "✍️ *របៀបពិនិត្យអក្ខរាវិរុទ្ធខ្មែរ (Chuon Nath Dictionary)៖*\n\n"
            "សូមវាយ៖ `/check <អត្ថបទខ្មែរ>`\n"
            "ឬ Reply លើសារណាមួយរួចវាយ `/check`\n\n"
            "AI នឹងជួយកែពាក្យខុសឱ្យត្រូវតាមវចនានុក្រមសម្តេច ជួន ណាត និងកែលម្អឃ្លាប្រយោគឱ្យកាន់តែពិរោះ!",
            parse_mode="Markdown"
        )
        return

    status_msg = await update.message.reply_text("🔍 *កំពុងពិនិត្យអក្ខរាវិរុទ្ធ និងវេយ្យាករណ៍...* ✍️", parse_mode="Markdown")
    try:
        result = await check_khmer_spelling(text)
        await safe_edit_text(status_msg, result)
    except Exception as e:
        logger.error(f"Check command error: {e}")
        await safe_edit_text(status_msg, f"❌ កំហុស៖ {str(e)[:120]}")

# -------------------------------------------------------------
# Pro Translation (English <-> Khmer) Handler
# -------------------------------------------------------------
async def translate_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Pro Translation: /translate <text>."""
    text = " ".join(context.args) if context.args else ""
    if not text and update.message.reply_to_message and update.message.reply_to_message.text:
        text = update.message.reply_to_message.text

    if not text:
        await update.message.reply_text(
            "🌐 *របៀបបកប្រែភាសា Pro (English ⬄ Khmer)៖*\n\n"
            "សូមវាយ៖ `/translate <អត្ថបទ>` (ឬកាត់ខ្លី `/tr <អត្ថបទ>`)\n"
            "ឬ Reply លើសារណាមួយរួចវាយ `/translate`\n\n"
            "Bot នឹងបកប្រែយ៉ាងលម្អិត រួមទាំងការពន្យល់ពាក្យគន្លឹះ និងការបញ្ចេញសំឡេង!",
            parse_mode="Markdown"
        )
        return

    status_msg = await update.message.reply_text("🌐 *កំពុងដំណើរការបកប្រែ Pro...*", parse_mode="Markdown")
    try:
        result = await translate_pro(text)
        await safe_edit_text(status_msg, result)
    except Exception as e:
        logger.error(f"Translate error: {e}")
        await safe_edit_text(status_msg, f"❌ កំហុស៖ {str(e)[:120]}")

# -------------------------------------------------------------
# Music Finder & MP3 Downloader Handler
# -------------------------------------------------------------
async def song_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Search & download song MP3: /song <query>."""
    query = " ".join(context.args) if context.args else ""
    if not query:
        await update.message.reply_text(
            "🎧 *របៀបស្វែងរក និងទាញយកចម្រៀង MP3 320kbps៖*\n\n"
            "សូមវាយ៖ `/song <ឈ្មោះបទចម្រៀង ឬឈ្មោះតារា>`\n\n"
            "• ឧទាហរណ៍៖ `/song ស្រលាញ់គ្នាម្តងទៀតបានទេ`\n"
            "• ឧទាហរណ៍៖ `/song shape of you`\n\n"
            "Bot នឹងស្វែងរក និងទាញយក file MP3 កម្រិតច្បាស់ជូនភ្លាមៗ!",
            parse_mode="Markdown"
        )
        return

    status_msg = await update.message.reply_text(
        f"🔍 *កំពុងស្វែងរក និងទាញយកបទចម្រៀង៖* `{query}` 🎶\n_សូមរង់ចាំប្រហែល ៥-១០ វិនាទី..._",
        parse_mode="Markdown"
    )
    await update.message.chat.send_action("upload_voice")

    from services.video_downloader import cleanup_file
    try:
        res = await download_song(query)
        file_path = res["file_path"]
        dur = int(res.get("duration", 0) or 0)
        
        await safe_edit_text(status_msg, f"📤 *ទាញយកបានសម្រេច!* កំពុងផ្ញើបទ `{res['title'][:35]}` ទៅ Telegram... 🎶")

        caption = (
            f"🎧 *{res['title']}*\n"
            f"👤 *តារាចម្រៀង:* {res['performer']}\n"
            f"⏱️ *រយៈពេល:* {res['duration_str']}\n\n"
            f"✨ Smart Assistant Bot 🎵"
        )

        with open(file_path, "rb") as audio_file:
            await update.message.reply_audio(
                audio=audio_file,
                title=res["title"],
                performer=res["performer"],
                duration=dur,
                caption=caption,
                parse_mode="Markdown",
                read_timeout=300.0,
                write_timeout=300.0,
                connect_timeout=60.0,
            )
        cleanup_file(file_path)
        try:
            import shutil
            shutil.rmtree(res["temp_dir"], ignore_errors=True)
            await status_msg.delete()
        except Exception:
            pass
    except asyncio.TimeoutError:
        logger.warning(f"Song download timed out for query: {query}")
        await safe_edit_text(status_msg, "❌ ការទាញយកចម្រៀងលើសម៉ោងកំណត់ (Timeout)។ សូមសាកល្បងម្តងទៀត ឬវាយឈ្មោះបទឱ្យកាន់តែច្បាស់។")
    except Exception as e:
        logger.error(f"Song download error: {e}")
        err_str = str(e).lower()
        if "timed out" in err_str or "timeout" in err_str:
            await safe_edit_text(status_msg, "❌ ការ Upload ឯកសារចម្រៀងទៅ Telegram យឺតលើសម៉ោងកំណត់។ សូមសាកល្បងម្ដងទៀត។")
        else:
            await safe_edit_text(status_msg, f"❌ មិនអាចទាញយកចម្រៀងបានទេ៖ {str(e)[:150]}")

# -------------------------------------------------------------
# AI Background Remover Handler
# -------------------------------------------------------------
async def rembg_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Remove background from a photo: /rembg."""
    photo = None
    if update.message.photo:
        photo = update.message.photo[-1]
    elif update.message.reply_to_message and update.message.reply_to_message.photo:
        photo = update.message.reply_to_message.photo[-1]

    if not photo:
        await update.message.reply_text(
            "✂️ *របៀបកាត់ផ្ទៃខាងក្រោយរូបភាព (AI Background Remover)៖*\n\n"
            "1. ផ្ញើរូបភាពដោយសរសេរ Caption ថា `/rembg`\n"
            "2. ឬ Reply លើរូបថតណាមួយដោយវាយ `/rembg`\n\n"
            "Bot នឹងកាត់ Background ចេញភ្លាមៗក្លាយជា File PNG Transparent!",
            parse_mode="Markdown"
        )
        return

    status_msg = await update.message.reply_text("✂️ *កំពុងកាត់ផ្ទៃខាងក្រោយរូបភាព (Background Remover)...*", parse_mode="Markdown")
    await update.message.chat.send_action("upload_document")
    try:
        tg_file = await context.bot.get_file(photo.file_id)
        raw_bytes = await tg_file.download_as_bytearray()
        png_fp = await remove_background(bytes(raw_bytes))

        png_fp.name = "transparent_cutout.png"
        await update.message.reply_document(
            document=png_fp,
            caption="✂️ *រូបភាពរបស់អ្នកត្រូវបានកាត់ផ្ទៃខាងក្រោយជោគជ័យ!* ✨\n_ជាទម្រង់ Transparent PNG_",
            parse_mode="Markdown"
        )
        try:
            await status_msg.delete()
        except Exception:
            pass
    except Exception as e:
        logger.error(f"Rembg error: {e}")
        await safe_edit_text(status_msg, f"❌ មិនអាចកាត់ background បានទេ៖ {str(e)[:120]}")

# -------------------------------------------------------------
# TikTok Sound Identifier Handler
# -------------------------------------------------------------
async def sound_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Identify soundtrack from TikTok/video URL: /sound <url>."""
    from services.video_downloader import extract_video_url
    url = context.args[0] if context.args else None
    if not url and update.message.reply_to_message and update.message.reply_to_message.text:
        url = extract_video_url(update.message.reply_to_message.text)

    if not url:
        await update.message.reply_text(
            "🔍 *របៀបស្វែងរកប្រភពបទភ្លេង (TikTok Sound Identifier)៖*\n\n"
            "សូមវាយ៖ `/sound <Link វីដេអូ TikTok>`\n"
            "ឬ Reply លើសារដែលមាន Link ដោយវាយ `/sound`\n\n"
            "Bot នឹងស្រង់យកឈ្មោះបទចម្រៀង និងតារាចម្រៀងដើមជូន!",
            parse_mode="Markdown"
        )
        return

    status_msg = await update.message.reply_text("🔍 *កំពុងស្រង់យកឈ្មោះបទចម្រៀងដើម...*", parse_mode="Markdown")
    try:
        sound_info = await identify_tiktok_sound(url)
        track = sound_info["track"]
        artist = sound_info["artist"]
        album = sound_info["album"]
        title = sound_info["title"]

        msg = (
            f"🎵 *ប្រភពបទភ្លេង / Soundtrack ដែលរកឃើញ៖* ✨\n\n"
            f"🎼 *ឈ្មោះបទ:* `{track}`\n"
            f"👤 *អ្នកបង្កើត/តារា:* `{artist}`\n"
            f"💿 *អាល់ប៊ុម:* `{album}`\n"
            f"🎬 *វីដេអូដើម:* {title[:60]}\n\n"
            f"💡 _អ្នកអាចវាយ_ `/song {track}` _ដើម្បីទាញយកបទពេញជា MP3 បាន!_"
        )
        await safe_edit_text(status_msg, msg)
    except Exception as e:
        logger.error(f"Sound identifier error: {e}")
        await safe_edit_text(status_msg, f"❌ មិនអាចស្គាល់បទភ្លេងក្នុងវីដេអូនេះទេ៖ {str(e)[:120]}")

# -------------------------------------------------------------
# Morning News Digest Handler
# -------------------------------------------------------------
async def news_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """View Morning News Digest with 'បង្ហាញសារថ្មី លុបសារចាស់': /news."""
    await update.message.chat.send_action("typing")
    status_msg = await send_clean_response(update, context, "📰 *កំពុងទាញយកព័ត៌មានជាតិ & បច្ចេកវិទ្យា...*")
    try:
        digest = await generate_morning_news_digest()
        if status_msg:
            await safe_edit_text(status_msg, digest, reply_markup=get_back_keyboard())
        else:
            await send_clean_response(update, context, digest, reply_markup=get_back_keyboard())
    except Exception as e:
        logger.error(f"News error: {e}")
        err_msg = f"❌ មិនអាចទាញយកព័ត៌មានបានទេ៖ {str(e)[:120]}"
        if status_msg:
            await safe_edit_text(status_msg, err_msg, reply_markup=get_back_keyboard())
        else:
            await send_clean_response(update, context, err_msg, reply_markup=get_back_keyboard())

# -------------------------------------------------------------
# Group Anti-Spam & Moderation Control Handler
# -------------------------------------------------------------
async def antispam_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Toggle Anti-Spam protection in Telegram groups: /antispam [on|off]."""
    chat = update.effective_chat
    user = update.effective_user

    if chat.type not in ["group", "supergroup"]:
        await update.message.reply_text("⚠️ *មុខងារនេះដំណើរការតែនៅក្នុង Group ឬ Supergroup ប៉ុណ្ណោះ!*", parse_mode="Markdown")
        return

    # Check if user is administrator
    try:
        member = await context.bot.get_chat_member(chat.id, user.id)
        if member.status not in ["creator", "administrator"] and user.id != ADMIN_USER_ID:
            await update.message.reply_text("⛔ *មានតែ Admin នៃ Group ប៉ុណ្ណោះដែលអាចកំណត់ Anti-Spam បាន!*", parse_mode="Markdown")
            return
    except Exception as e:
        logger.warning(f"Failed to check member status: {e}")

    arg = (context.args[0] if context.args else "").lower()
    if arg in ["on", "enable", "បើក"]:
        set_antispam_enabled(chat.id, True)
        await update.message.reply_text(
            "🛡️ *ប្រព័ន្ធការពារ Spam & Casino Ads ត្រូវបាន [បើក] ជោគជ័យ!* ✅\n\n"
            "Bot នឹងស្វែងរក និងលុបសារផ្សាយពាណិជ្ជកម្មល្បែងស៊ីសង (កាស៊ីណូ, បាការ៉ាត់, ស្លុត) "
            "និង Link មេរោគដោយស្វ័យប្រវត្តិ។",
            parse_mode="Markdown"
        )
    elif arg in ["off", "disable", "បិទ"]:
        set_antispam_enabled(chat.id, False)
        await update.message.reply_text(
            "⚠️ *ប្រព័ន្ធការពារ Spam & Casino Ads ត្រូវបាន [បិទ]!*",
            parse_mode="Markdown"
        )
    else:
        current_status = is_antispam_enabled(chat.id)
        status_str = "✅ កំពុងបើក (Active)" if current_status else "❌ បានបិទ (Disabled)"
        await update.message.reply_text(
            f"🛡️ *ការកំណត់ប្រព័ន្ធការពារ Spam ក្នុង Group៖*\n\n"
            f"• ស្ថានភាពបច្ចុប្បន្ន៖ *{status_str}*\n\n"
            f"👉 របៀបកំណត់៖\n"
            f"• `/antispam on` ➔ ដើម្បីបើក\n"
            f"• `/antispam off` ➔ ដើម្បីបិទ",
            parse_mode="Markdown"
        )

# -------------------------------------------------------------
# Welcome Banner Control Handler
# -------------------------------------------------------------
async def welcome_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Toggle Auto Welcome Banner in Telegram groups: /welcome [on|off]."""
    chat = update.effective_chat
    user = update.effective_user

    if chat.type not in ["group", "supergroup"]:
        await update.message.reply_text("⚠️ *មុខងារនេះដំណើរការតែនៅក្នុង Group ឬ Supergroup ប៉ុណ្ណោះ!*", parse_mode="Markdown")
        return

    try:
        member = await context.bot.get_chat_member(chat.id, user.id)
        if member.status not in ["creator", "administrator"] and user.id != ADMIN_USER_ID:
            await update.message.reply_text("⛔ *មានតែ Admin នៃ Group ប៉ុណ្ណោះដែលអាចកំណត់ Welcome Banner បាន!*", parse_mode="Markdown")
            return
    except Exception as e:
        logger.warning(f"Failed to check member status: {e}")

    arg = (context.args[0] if context.args else "").lower()
    if arg in ["on", "enable", "បើក"]:
        set_welcome_enabled(chat.id, True)
        await update.message.reply_text(
            "🖼️ *រូបភាពស្វាគមន៍សមាជិកថ្មី (Welcome Banner) ត្រូវបាន [បើក] ជោគជ័យ!* ✅\n\n"
            "Bot នឹងបង្កើតរូបភាព Welcome Banner ស្អាតៗ ដោយមាន Profile Picture និងឈ្មោះសមាជិកថ្មីដោយស្វ័យប្រវត្តិ។",
            parse_mode="Markdown"
        )
    elif arg in ["off", "disable", "បិទ"]:
        set_welcome_enabled(chat.id, False)
        await update.message.reply_text(
            "⚠️ *រូបភាពស្វាគមន៍សមាជិកថ្មី (Welcome Banner) ត្រូវបាន [បិទ]!*",
            parse_mode="Markdown"
        )
    else:
        current_status = is_welcome_enabled(chat.id)
        status_str = "✅ កំពុងបើក (Active)" if current_status else "❌ បានបិទ (Disabled)"
        await update.message.reply_text(
            f"🖼️ *ការកំណត់ Welcome Banner ក្នុង Group៖*\n\n"
            f"• ស្ថានភាពបច្ចុប្បន្ន៖ *{status_str}*\n\n"
            f"👉 របៀបកំណត់៖\n"
            f"• `/welcome on` ➔ ដើម្បីបើក\n"
            f"• `/welcome off` ➔ ដើម្បីបិទ",
            parse_mode="Markdown"
        )

# -------------------------------------------------------------
# New Chat Members Auto-Welcome Handler
# -------------------------------------------------------------
async def handle_new_chat_members(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generate and send custom high-definition welcome banner for new group members."""
    chat = update.effective_chat
    if not update.message or not update.message.new_chat_members:
        return

    if not is_welcome_enabled(chat.id):
        return

    import io
    for new_member in update.message.new_chat_members:
        if new_member.is_bot:
            continue

        try:
            # Try fetching user avatar
            avatar_bytes = None
            photos = await context.bot.get_user_profile_photos(new_member.id, limit=1)
            if photos and photos.total_count > 0:
                photo_file = await context.bot.get_file(photos.photos[0][-1].file_id)
                avatar_bytes = bytes(await photo_file.download_as_bytearray())

            # Member count
            count = None
            try:
                count = await context.bot.get_chat_member_count(chat.id)
            except Exception:
                pass

            banner_bytes = generate_welcome_banner(
                user_name=new_member.full_name or "New Member",
                group_title=chat.title or "Our Group",
                avatar_bytes=avatar_bytes,
                member_count=count
            )

            caption = (
                f"🎉 *សូមស្វាគមន៍មកកាន់ {chat.title}!* 🤝\n\n"
                f"👋 សួស្តី [{new_member.full_name}](tg://user?id={new_member.id})! រីករាយដែលបានចូលរួមជាមួយពួកយើង។\n"
                f"✨ សូមរីករាយ និងគោរពតាមបទបញ្ជាផ្ទៃក្នុងរបស់គ្រុបណា៎! 🙌"
            )

            await update.message.reply_photo(
                photo=io.BytesIO(banner_bytes),
                caption=caption,
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.error(f"Error sending welcome banner: {e}")

# -------------------------------------------------------------
# Chat with PDF & PDF Summarizer Handlers
# -------------------------------------------------------------
async def pdf_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """View PDF helper or ask question about active PDF session: /pdf [question]."""
    chat_id = update.effective_chat.id
    
    # Check if this command is replying to a PDF document
    reply_msg = update.message.reply_to_message
    if reply_msg and reply_msg.document:
        doc = reply_msg.document
        if (doc.mime_type and "pdf" in doc.mime_type.lower()) or (doc.file_name and doc.file_name.lower().endswith(".pdf")):
            fake_update = Update(update.update_id, message=reply_msg)
            await handle_pdf_document(fake_update, context)
            return

    # Check if user asked a question about active PDF session
    question = " ".join(context.args).strip() if context.args else ""
    if question:
        session = get_pdf_session(chat_id)
        if session:
            await update.message.chat.send_action("typing")
            status = await update.message.reply_text(f"🔍 *កំពុងស្វែងរកចម្លើយក្នុងឯកសារ '{session['filename']}'...*", parse_mode="Markdown")
            ans = await answer_pdf_question(session.get("extracted_text") or session.get("summary", ""), question, session.get("filename", ""))
            await safe_edit_text(status, ans)
            return
        else:
            await update.message.reply_text(
                "⚠️ *មិនទាន់មានឯកសារ PDF ណាមួយត្រូវបាន Upload ទេ!*\n\n"
                "👉 សូមផ្ញើ ឬ Forward File PDF ចូលមកកាន់ Bot ជាមុនសិនណា៎។",
                parse_mode="Markdown"
            )
            return

    # Help message
    help_msg = (
        "📄 *ជំនួយការឯកសារ PDF & Chat with PDF (/pdf)* 🇰🇭\n\n"
        "👉 *របៀបប្រើប្រាស់ងាយៗ៖*\n"
        "1. **ផ្ញើ ឬ Forward File PDF ចូលមកកាន់ Bot** (កិច្ចសន្យា, សៀវភៅ, មេរៀន, ឬរបាយការណ៍)\n"
        "2. Bot នឹងអាន និងសង្ខេបចំណុចសំខាន់ៗជាភាសាខ្មែរភ្លាមៗ\n"
        "3. បន្ទាប់មក បងអាច **Reply លើសារសង្ខេប** ឬវាយ `/pdf <សំណួរ>` ដើម្បីសួរលម្អិតពីទំព័រណាមួយបាន!\n\n"
        "💡 _គាំទ្រឯកសារ PDF រហូតដល់ 20 MB យ៉ាងរលូន។_"
    )
    await safe_reply_text(update.message, help_msg)

async def handle_pdf_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle uploaded or forwarded PDF document: summarize and start Q&A session."""
    doc = update.message.document
    if not doc:
        return

    is_pdf = (doc.mime_type and "pdf" in doc.mime_type.lower()) or (doc.file_name and doc.file_name.lower().endswith(".pdf"))
    if not is_pdf:
        return

    if doc.file_size and doc.file_size > 25 * 1024 * 1024:
        await update.message.reply_text("⚠️ *ទំហំ File PDF លើសពី 25 MB!* សូមផ្ញើ file ដែលមានទំហំតូចជាងនេះ។", parse_mode="Markdown")
        return

    chat_id = update.effective_chat.id
    filename = doc.file_name or "document.pdf"
    await update.message.chat.send_action("typing")
    status_msg = await update.message.reply_text(f"📄 *AI កំពុងអាន និងសង្ខេបឯកសារ '{filename}'...* ⏳", parse_mode="Markdown")

    try:
        tg_file = await context.bot.get_file(doc.file_id)
        pdf_bytes = bytes(await tg_file.download_as_bytearray())
        summary, pdf_info = await analyze_and_summarize_pdf(pdf_bytes, filename)
        
        # Save session for follow-up chat
        save_pdf_session(
            chat_id=chat_id,
            filename=filename,
            summary=summary,
            extracted_text=pdf_info.get("text", ""),
            total_pages=pdf_info.get("total_pages", 1)
        )

        await safe_edit_text(status_msg, summary)
    except Exception as e:
        logger.error(f"Error analyzing PDF document: {e}")
        await safe_edit_text(status_msg, f"❌ កំហុសក្នុងការអាន PDF៖ {str(e)[:140]}")

# -------------------------------------------------------------
# AI Image Upscaler & Enhancer Handler
# -------------------------------------------------------------
async def enhance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Upscale and enhance image to crystal clear HD quality: /enhance or /upscale."""
    import io
    target_msg = update.message.reply_to_message if update.message.reply_to_message else update.message
    photos = target_msg.photo if target_msg else None

    if not photos:
        await update.message.reply_text(
            "🔍 *របៀបប្រើប្រាស់ AI Image Enhancer (ធ្វើឱ្យរូបច្បាស់ HD)៖*\n\n"
            "👉 ផ្ញើរូបភាពដោយភ្ជាប់ពាក្យ `/enhance` ក្នុង Caption\n"
            "👉 ឬចុច **Reply** លើរូបភាពណាមួយ រួចវាយពាក្យ `/enhance` ឬ `/upscale`\n\n"
            "Bot នឹងជួយសម្អាត Noise, ពង្រីកទំហំ 2x-4x និងធ្វើឱ្យរូបភាពកាន់តែច្បាស់ភ្លាមៗ! ✨",
            parse_mode="Markdown"
        )
        return

    photo = photos[-1]
    await update.message.chat.send_action("upload_photo")
    status = await update.message.reply_text("🔍 *កំពុងសម្អាត Noise និងបង្កើនគុណភាពរូបភាព HD...* ⏳", parse_mode="Markdown")

    try:
        tg_file = await context.bot.get_file(photo.file_id)
        img_bytes = bytes(await tg_file.download_as_bytearray())
        enhanced_bytes, metrics = enhance_image(img_bytes)

        caption = (
            f"✨ *រូបភាពរបស់អ្នកត្រូវបានបង្កើនគុណភាព HD រួចរាល់!* 🔍\n\n"
            f"📐 *ទំហំដើម:* `{metrics['orig_width']} x {metrics['orig_height']}` px\n"
            f"📈 *ទំហំថ្មី (HD):* `{metrics['new_width']} x {metrics['new_height']}` px (+{metrics['scale']}x)\n"
            f"⚡ *រយៈពេលដំណើរការ:* `{metrics['elapsed_seconds']}s`"
        )

        await update.message.reply_photo(
            photo=io.BytesIO(enhanced_bytes),
            caption=caption,
            parse_mode="Markdown"
        )
        try:
            await status.delete()
        except Exception:
            pass
    except Exception as e:
        logger.error(f"Image enhancement error: {e}")
        await safe_edit_text(status, f"❌ មិនអាចបង្កើនគុណភាពរូបភាពបានទេ៖ {str(e)[:120]}")

# -------------------------------------------------------------
# Watermark & Brand Protection Handler
# -------------------------------------------------------------
async def watermark_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Add professional watermark to image: /watermark <text>."""
    import io
    watermark_text = " ".join(context.args).strip() if context.args else ""
    target_msg = update.message.reply_to_message if update.message.reply_to_message else update.message
    photos = target_msg.photo if target_msg else None

    if not photos:
        await update.message.reply_text(
            "💧 *របៀបប្រើប្រាស់ Watermark បោះត្រាការពាររូបភាពទំនិញ៖*\n\n"
            "👉 ផ្ញើរូបភាពដោយភ្ជាប់ពាក្យ `/watermark <ឈ្មោះហាង លេខទូរស័ព្ទ>` ក្នុង Caption\n"
            "👉 ឬចុច **Reply** លើរូបភាពណាមួយ រួចវាយ `/watermark <ឈ្មោះហាង លេខទូរស័ព្ទ>`\n\n"
            "ឧទាហរណ៍៖ `/watermark ហាង ពិសិដ្ឋ 012 345 678`\n"
            "Bot នឹងបោះត្រាការពាររូបភាពកម្រិត Professional ជូនភ្លាមៗ! 🛡️",
            parse_mode="Markdown"
        )
        return

    if not watermark_text:
        watermark_text = update.effective_user.first_name or "My Store"

    photo = photos[-1]
    await update.message.chat.send_action("upload_photo")
    status = await update.message.reply_text(f"💧 *កំពុងបោះត្រា Watermark '{watermark_text}' លើរូបភាព...* ⏳", parse_mode="Markdown")

    try:
        tg_file = await context.bot.get_file(photo.file_id)
        img_bytes = bytes(await tg_file.download_as_bytearray())
        watermarked_bytes = apply_watermark(img_bytes, text=watermark_text)

        await update.message.reply_photo(
            photo=io.BytesIO(watermarked_bytes),
            caption=f"🛡️ *រូបភាពរបស់អ្នកត្រូវបានបោះត្រាការពារដោយជោគជ័យ!* ✨\n_Watermark: {watermark_text}_",
            parse_mode="Markdown"
        )
        try:
            await status.delete()
        except Exception:
            pass
    except Exception as e:
        logger.error(f"Watermark error: {e}")
        await safe_edit_text(status, f"❌ មិនអាចបោះត្រាលើរូបភាពបានទេ៖ {str(e)[:120]}")


# -------------------------------------------------------------
# Safe Message Sender & Editor (Protects against Markdown parse errors)
# -------------------------------------------------------------
async def safe_reply_text(message, text: str, reply_markup=None, parse_mode="Markdown"):
    """Safely reply with markdown; fallback to plain text if Telegram fails entity parsing."""
    try:
        return await message.reply_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
    except Exception as e:
        err_str = str(e).lower()
        if "parse entities" in err_str or "entity" in err_str:
            return await message.reply_text(text, reply_markup=reply_markup, parse_mode=None)
        raise

async def safe_edit_text(message, text: str, reply_markup=None, parse_mode="Markdown"):
    """Safely edit with markdown; fallback to plain text if Telegram fails entity parsing."""
    try:
        return await message.edit_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
    except Exception as e:
        err_str = str(e).lower()
        if "parse entities" in err_str or "entity" in err_str:
            return await message.edit_text(text, reply_markup=reply_markup, parse_mode=None)
        raise

# -------------------------------------------------------------
# Media Handlers (Voice & Vision)
# -------------------------------------------------------------
async def handle_voice_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle voice messages using Gemini 2.5 Flash audio understanding."""
    voice = update.message.voice or update.message.audio
    if not voice:
        return
        
    await update.message.chat.send_action("typing")
    status = await update.message.reply_text("🎙️ *កំពុងស្តាប់សារសំឡេងរបស់អ្នក...* 🎧", parse_mode="Markdown")
    
    try:
        tg_file = await context.bot.get_file(voice.file_id)
        voice_bytes = await tg_file.download_as_bytearray()
        
        reply_text = await process_voice_ai(bytes(voice_bytes), mime_type="audio/ogg")
        await safe_edit_text(status, reply_text)
    except Exception as e:
        logger.error(f"Error handling voice message: {e}")
        await safe_edit_text(status, f"❌ មិនអាចដំណើរការសារជាសំឡេងបានទេ៖ {str(e)[:100]}")

async def handle_photo_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle photo messages for QR reading or Vision OCR."""
    photos = update.message.photo
    if not photos:
        return
        
    # Get highest resolution
    photo = photos[-1]
    caption = update.message.caption or ""
    
    await update.message.chat.send_action("typing")
    
    try:
        tg_file = await context.bot.get_file(photo.file_id)
        img_bytes = bytes(await tg_file.download_as_bytearray())
        
        # 1. Check for EXIF GPS metadata in photo
        gps_coords = extract_gps_from_image_bytes(img_bytes)
        caption_lower = caption.lower()
        is_loc_request = any(k in caption_lower for k in ["/loc", "/location", "ទីតាំង", "កន្លែង", "ផែនទី", "gps", "where", "location"])

        if gps_coords:
            lat, lon = gps_coords
            status = await update.message.reply_text("📍 *បានរកឃើញ GPS ក្នុងរូបភាព! កំពុងទាញយកព័ត៌មានទីតាំង...* 🛰️", parse_mode="Markdown")
            loc_info = await get_detailed_cambodia_location(lat, lon)
            w_data = await fetch_weather(lat, lon)
            temp_str = None
            if w_data and "current" in w_data:
                curr = w_data["current"]
                temp_str = f"*{curr.get('temperature_2m')}°C* (ខ្យល់: {curr.get('wind_speed_10m')} km/h)"
            loc_msg = format_photo_gps_message(loc_info, temp_str)
            maps_url = f"https://www.google.com/maps?q={lat},{lon}"
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("🗺️ បើកមើលលើ Google Maps", url=maps_url)],
                [InlineKeyboardButton("🔙 Menu ដើម", callback_data="btn_back_main")]
            ])
            await safe_edit_text(status, loc_msg, reply_markup=kb)
            try:
                await update.message.reply_location(latitude=lat, longitude=lon)
            except Exception as e_loc:
                logger.warning(f"Could not send native location: {e_loc}")
            return

        if is_loc_request:
            # User specifically requested location identification
            status = await update.message.reply_text("🔍 *កំពុងពិនិត្យមើលស្លាកសញ្ញា សំណង់ និងទីតាំងក្នុងរូបភាព (AI Geolocation)...* 🛰️", parse_mode="Markdown")
            vision_loc = await identify_location_via_vision(img_bytes, caption=caption)
            loc_action_kb = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("🧹 សម្អាតសារ", callback_data="btn_clean_chat"),
                    InlineKeyboardButton("🔙 Menu ដើម", callback_data="btn_back_main")
                ]
            ])
            await safe_edit_text(status, vision_loc, reply_markup=loc_action_kb)
            return

        # Check if caption requests image enhancement (HD Upscaler)
        caption_lower = caption.lower()
        if "/enhance" in caption_lower or "/upscale" in caption_lower or "ច្បាស់" in caption_lower:
            status = await update.message.reply_text("🔍 *កំពុងសម្អាត Noise និងបង្កើនគុណភាពរូបភាព HD...* ⏳", parse_mode="Markdown")
            import io
            enhanced_bytes, metrics = enhance_image(img_bytes)
            caption_out = (
                f"✨ *រូបភាពរបស់អ្នកត្រូវបានបង្កើនគុណភាព HD រួចរាល់!* 🔍\n\n"
                f"📐 *ទំហំដើម:* `{metrics['orig_width']} x {metrics['orig_height']}` px\n"
                f"📈 *ទំហំថ្មី (HD):* `{metrics['new_width']} x {metrics['new_height']}` px (+{metrics['scale']}x)\n"
                f"⚡ *រយៈពេលដំណើរការ:* `{metrics['elapsed_seconds']}s`"
            )
            await update.message.reply_photo(photo=io.BytesIO(enhanced_bytes), caption=caption_out, parse_mode="Markdown")
            try:
                await status.delete()
            except Exception:
                pass
            return

        # Check if caption requests watermark
        if "/watermark" in caption_lower or "watermark" in caption_lower or "បោះត្រា" in caption_lower:
            status = await update.message.reply_text("💧 *កំពុងបោះត្រា Watermark លើរូបភាព...* ⏳", parse_mode="Markdown")
            import io
            clean_wm = caption.replace("/watermark", "").replace("watermark", "").replace("បោះត្រា", "").strip()
            if not clean_wm:
                clean_wm = update.effective_user.first_name or "My Store"
            watermarked_bytes = apply_watermark(img_bytes, text=clean_wm)
            await update.message.reply_photo(
                photo=io.BytesIO(watermarked_bytes),
                caption=f"🛡️ *រូបភាពរបស់អ្នកត្រូវបានបោះត្រាការពារដោយជោគជ័យ!* ✨\n_Watermark: {clean_wm}_",
                parse_mode="Markdown"
            )
            try:
                await status.delete()
            except Exception:
                pass
            return

        # Check if caption requests background removal
        if "/rembg" in caption_lower or "កាត់" in caption_lower or "background" in caption_lower:
            status = await update.message.reply_text("✂️ *កំពុងកាត់ផ្ទៃខាងក្រោយរូបភាព (Background Remover)...*", parse_mode="Markdown")
            await update.message.chat.send_action("upload_document")
            png_fp = await remove_background(img_bytes)
            png_fp.name = "transparent_cutout.png"
            await update.message.reply_document(
                document=png_fp,
                caption="✂️ *រូបភាពរបស់អ្នកត្រូវបានកាត់ផ្ទៃខាងក្រោយជោគជ័យ!* ✨\n_ជាទម្រង់ Transparent PNG_",
                parse_mode="Markdown"
            )
            try:
                await status.delete()
            except Exception:
                pass
            return

        # 1. First check if it's a QR code / KHQR
        qr_text = read_qr_code(img_bytes)
        if qr_text and not caption:
            is_url = qr_text.startswith("http://") or qr_text.startswith("https://")
            buttons = []
            if is_url:
                buttons.append([InlineKeyboardButton("🌐 បើក Link", url=qr_text)])
            buttons.append([InlineKeyboardButton("🔙 Menu ដើម", callback_data="btn_back_main")])
            
            msg = (
                "📷 *បានរកឃើញ QR Code / KHQR!* 🔍\n\n"
                f"📝 *ទិន្នន័យ (Decoded Data)៖*\n`{qr_text}`\n\n"
                "💡 _លោកអ្នកអាច Copy ឬបើកមើល Link នេះបានភ្លាមៗ!_"
            )
            await safe_reply_text(
                update.message,
                msg,
                reply_markup=InlineKeyboardMarkup(buttons)
            )
            return
            
        # 2. Otherwise process with Gemini Vision OCR / AI
        status = await update.message.reply_text("📷 *AI កំពុងអាន និងវិភាគរូបភាពរបស់អ្នក...* 🔍", parse_mode="Markdown")
        reply_text = await process_vision_ai(img_bytes, mime_type="image/jpeg", caption=caption)
        photo_action_kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("📍 ស្វែងរកទីតាំង (GPS)", callback_data="btn_photo_loc_help"),
                InlineKeyboardButton("🔍 ធ្វើឱ្យច្បាស់ HD", callback_data="btn_photo_enhance_help"),
            ],
            [
                InlineKeyboardButton("💧 ដាក់ Watermark", callback_data="btn_photo_watermark_help"),
                InlineKeyboardButton("✂️ កាត់ Background", callback_data="btn_photo_rembg_help"),
            ],
            [
                InlineKeyboardButton("🔙 Menu ដើម", callback_data="btn_back_main"),
            ]
        ])
        await safe_edit_text(status, reply_text, reply_markup=photo_action_kb)
        
    except Exception as e:
        logger.error(f"Error handling photo: {e}")
        await safe_reply_text(update.message, f"❌ កំហុសក្នុងការដំណើរការរូបភាព៖ {str(e)[:100]}")

async def handle_document_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle uncompressed photos sent as File/Document to preserve full camera EXIF GPS tags."""
    doc = update.message.document
    if not doc:
        return

    mime = (doc.mime_type or "").lower()
    fname = (doc.file_name or "").lower()
    is_img = mime.startswith("image/") or any(fname.endswith(ext) for ext in [".jpg", ".jpeg", ".png", ".heic", ".webp"])
    if not is_img:
        return

    if doc.file_size and doc.file_size > 25 * 1024 * 1024:
        return

    await update.message.chat.send_action("typing")
    try:
        tg_file = await context.bot.get_file(doc.file_id)
        img_bytes = bytes(await tg_file.download_as_bytearray())
        caption = update.message.caption or ""

        # Check for EXIF GPS
        gps_coords = extract_gps_from_image_bytes(img_bytes)
        if gps_coords:
            lat, lon = gps_coords
            status = await update.message.reply_text("📍 *បានរកឃើញ GPS ក្នុង File រូបភាព! កំពុងទាញយកទីតាំង...* 🛰️", parse_mode="Markdown")
            loc_info = await get_detailed_cambodia_location(lat, lon)
            w_data = await fetch_weather(lat, lon)
            temp_str = None
            if w_data and "current" in w_data:
                curr = w_data["current"]
                temp_str = f"*{curr.get('temperature_2m')}°C* (ខ្យល់: {curr.get('wind_speed_10m')} km/h)"
            loc_msg = format_photo_gps_message(loc_info, temp_str)
            maps_url = f"https://www.google.com/maps?q={lat},{lon}"
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("🗺️ បើកមើលលើ Google Maps", url=maps_url)],
                [InlineKeyboardButton("🔙 Menu ដើម", callback_data="btn_back_main")]
            ])
            await safe_edit_text(status, loc_msg, reply_markup=kb)
            try:
                await update.message.reply_location(latitude=lat, longitude=lon)
            except Exception as e_loc:
                logger.warning(f"Could not send native location: {e_loc}")
            return

        # If no GPS, but caption requests location
        caption_lower = caption.lower()
        if any(k in caption_lower for k in ["/loc", "/location", "ទីតាំង", "កន្លែង", "ផែនទី", "gps", "where", "location"]):
            status = await update.message.reply_text("🔍 *កំពុងវិភាគទីតាំងក្នុងរូបភាព (AI Geolocation)...* 🛰️", parse_mode="Markdown")
            vision_loc = await identify_location_via_vision(img_bytes, caption=caption)
            loc_action_kb = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("🧹 សម្អាតសារ", callback_data="btn_clean_chat"),
                    InlineKeyboardButton("🔙 Menu ដើម", callback_data="btn_back_main")
                ]
            ])
            await safe_edit_text(status, vision_loc, reply_markup=loc_action_kb)
            return

    except Exception as e:
        logger.error(f"Error handling document image: {e}")

# -------------------------------------------------------------
# Existing Weather, Calendar & Alert Commands
# -------------------------------------------------------------
async def weather_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /weather command to check weather immediately with 'បង្ហាញសារថ្មី លុបសារចាស់'."""
    chat_id = update.effective_chat.id
    settings = get_user_weather_settings(chat_id)
    lat = settings.get("latitude") or DEFAULT_LAT
    lon = settings.get("longitude") or DEFAULT_LON
    loc_name = settings.get("location_name") or DEFAULT_LOCATION_NAME
    
    await update.message.chat.send_action("typing")
    w_data = await fetch_weather(lat, lon)
    if not w_data:
        await send_clean_response(update, context, "❌ មិនអាចទាញយកព័ត៌មានអាកាសធាតុបានទេ សូមព្យាយាមម្តងទៀត។", reply_markup=get_back_keyboard())
        return
        
    msg = format_weather_message(w_data, loc_name, is_daily_alert=False)
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📍 ប្ដូរទីតាំង", callback_data="btn_location_menu"),
            InlineKeyboardButton("🔙 Menu ដើម", callback_data="btn_back_main")
        ]
    ])
    await send_clean_response(update, context, msg, reply_markup=keyboard)

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
    await send_clean_response(
        update, context,
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
        await send_clean_response(update, context, "❌ មិនអាចទាញយកព័ត៌មានអាកាសធាតុបានទេ។", reply_markup=get_back_keyboard())
        return
        
    msg = (
        "🧪 *[សារតេស្តសាកល្បង - 5:00 AM Weather Alert Preview]*\n\n"
        + format_weather_message(w_data, loc_name, is_daily_alert=True)
    )
    await send_clean_response(update, context, msg, reply_markup=get_back_keyboard(), parse_mode="Markdown")

async def handle_location_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle GPS location sent by user with full Cambodian administrative hierarchy."""
    loc = update.message.location
    if not loc:
        return
        
    chat = update.effective_chat
    lat = loc.latitude
    lon = loc.longitude
    
    await chat.send_action("typing")
    loc_info = await get_detailed_cambodia_location(lat, lon)
    loc_short_name = loc_info.get("short_name") or f"{lat:.4f}, {lon:.4f}"
    
    set_user_location(chat.id, lat, lon, loc_short_name)
    set_weather_alert_active(chat.id, True)
    
    w_data = await fetch_weather(lat, lon)
    weather_text = format_weather_message(w_data, loc_short_name, is_daily_alert=False) if w_data else ""
    
    reply_text = format_detailed_location_message(loc_info, weather_text)
    await send_clean_response(
        update, context,
        reply_text,
        reply_markup=get_back_keyboard()
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command with 'បង្ហាញសារថ្មី លុបសារចាស់'."""
    help_text = (
        "💡 *បញ្ជី Command ពេញលេញសម្រាប់ប្រើប្រាស់៖*\n\n"
        "🔹 `/start` - បើកផ្ទាំង Dashboard មេ\n"
        "🔹 `/finance` - មើលអត្រាប្តូរប្រាក់ តម្លៃមាស និងតម្លៃសាំង\n"
        "🔹 `/budget` - មើលរបាយការណ៍ចំណូល-ចំណាយ\n"
        "🔹 `/convert 100 USD KHR` - គណនាប្តូរប្រាក់រហ័ស\n"
        "🔹 `/remind 08:30 ជួបភ្ញៀវ` - កំណត់ម៉ោងរំលឹកកិច្ចការ\n"
        "🔹 `/reminders` - មើលបញ្ជីសារដាស់តឿនរបស់អ្នក\n"
        "🔹 `/clean` - សម្អាតសារចាស់ៗទាំងអស់\n"
        "🔹 `/weather` - មើលអាកាសធាតុបច្ចុប្បន្ន\n"
        "🔹 `/location` - កំណត់ទីតាំងអាកាសធាតុ 5AM\n"
        "🔹 `/upcoming` - មើលថ្ងៃបុណ្យដែលខិតជិតមកដល់\n"
        "🔹 `/calendar` - មើលប្រតិទិនឈប់សម្រាកប្រចាំឆ្នាំ\n"
        "🔹 `/aimode` - បើក/បិទ AI Continuous Chat Mode\n"
        "🔹 `/song <ឈ្មោះបទ>` - ទាញយកចម្រៀង MP3 320kbps\n"
        "🔹 `/enhance` - ធ្វើឱ្យរូបភាពច្បាស់ HD\n"
        "🔹 `/watermark` - បោះត្រាការពាររូបភាពផលិតផល\n"
        "🔹 `/pdf` - Chat with PDF សង្ខេប និងឆ្លើយសំណួរ\n"
        "🔹 `/status` - ពិនិត្យស្ថានភាពគណនី\n\n"
        "📥 *Video:* Copy Link (TikTok/YouTube/FB) ផ្ញើចូលទីនេះភ្លាមៗ!"
    )
    await send_clean_response(update, context, help_text, reply_markup=get_back_keyboard(), parse_mode="Markdown")

async def upcoming_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /upcoming command with 'បង្ហាញសារថ្មី លុបសារចាស់'."""
    msg = format_upcoming_message()
    await send_clean_response(update, context, msg, reply_markup=get_back_keyboard(), parse_mode="Markdown")

async def calendar_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /calendar command with 'បង្ហាញសារថ្មី លុបសារចាស់'."""
    current_year = datetime.now(BOT_TIMEZONE).year
    keyboard = [
        [
            InlineKeyboardButton("ឆ្នាំ ២០២៥", callback_data="btn_calendar_2025"),
            InlineKeyboardButton("ឆ្នាំ ២០២៦", callback_data="btn_calendar_2026"),
            InlineKeyboardButton("ឆ្នាំ ២០២៧", callback_data="btn_calendar_2027"),
        ],
        [InlineKeyboardButton("🔙 ត្រឡប់ទៅ Menu ដើម", callback_data="btn_back_main")]
    ]
    msg = format_calendar_message(current_year)
    await send_clean_response(update, context, msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def subscribe_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /subscribe command with 'បង្ហាញសារថ្មី លុបសារចាស់'."""
    chat = update.effective_chat
    user = update.effective_user
    add_subscriber(chat.id, user.username if user else None, chat.type)
    await send_clean_response(
        update, context,
        "✅ *បានបើកការដាស់តឿនដោយជោគជ័យ!*\n\n"
        "Bot នឹងផ្ញើសារជូនដំណឹងនៅម៉ោង *៤:០០ ព្រឹក* (ម៉ោងនៅកម្ពុជា) រាល់ពេលមានថ្ងៃឈប់សម្រាកបុណ្យជាតិ 🇰🇭",
        reply_markup=get_back_keyboard(),
        parse_mode="Markdown"
    )

async def unsubscribe_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /unsubscribe command with 'បង្ហាញសារថ្មី លុបសារចាស់'."""
    chat = update.effective_chat
    remove_subscriber(chat.id)
    await send_clean_response(
        update, context,
        "🔕 *បានបិទការដាស់តឿនបុណ្យជាតិរួចរាល់ហើយ។*\nអ្នកអាចបើកវិញបានគ្រប់ពេលដោយប្រើ `/subscribe`។",
        reply_markup=get_back_keyboard(),
        parse_mode="Markdown"
    )

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /status command with 'បង្ហាញសារថ្មី លុបសារចាស់'."""
    chat_id = update.effective_chat.id
    user = update.effective_user
    subscribed = is_subscribed(chat_id)
    today_holiday = get_today_holiday()
    today_date = get_current_cambodia_date()
    
    w_settings = get_user_weather_settings(chat_id)
    loc_name = w_settings.get("location_name", "ភ្នំពេញ")
    weather_active = w_settings.get("is_active", True)
    ai_active = is_ai_mode(chat_id)
    rems = get_user_reminders(chat_id)
    
    first_name = user.full_name if user else "អ្នកប្រើប្រាស់"
    status_text = (
        "📊 *ស្ថានភាពគណនីរបស់អ្នក (Account Status)*\n\n"
        f"👤 ឈ្មោះ: *{first_name}*\n"
        f"🆔 Telegram ID: `{chat_id}`\n"
        f"📅 កាលបរិច្ឆេទ: `{today_date}` (Asia/Phnom_Penh)\n"
        f"📍 ទីតាំងអាកាសធាតុ: *{loc_name}*\n"
        f"🌅 ដំណឹងអាកាសធាតុ ៥:០០ ព្រឹក: {'✅ កំពុងបើក (Active)' if weather_active else '❌ បានបិទ (Inactive)'}\n"
        f"🔔 ដំណឹងបុណ្យជាតិ ៤:០០ ព្រឹក: {'✅ កំពុងបើក (Active)' if subscribed else '❌ បានបិទ (Inactive)'}\n"
        f"💬 AI Continuous Chat: {'✅ កំពុងបើក (Active)' if ai_active else '❌ បានបិទ (Inactive)'}\n"
        f"⏰ Reminders កំពុងរង់ចាំ: *{len(rems)}* កិច្ចការ\n"
        f"🎉 ថ្ងៃឈប់សម្រាកថ្ងៃនេះ: {today_holiday['name_km'] if today_holiday else 'ពុំមែនជាថ្ងៃឈប់សម្រាកទេ'}\n"
    )
    await send_clean_response(update, context, status_text, reply_markup=get_back_keyboard(), parse_mode="Markdown")

async def test_alert_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /test_alert command with 'បង្ហាញសារថ្មី លុបសារចាស់'."""
    upcoming = get_upcoming_holidays(limit=1)
    sample_holiday = upcoming[0] if upcoming else {
        "date": "2026-04-14",
        "name_km": "ពិធីបុណ្យចូលឆ្នាំថ្មីប្រពៃណីជាតិ",
        "name_en": "Khmer New Year",
        "wishes": "សួស្តីឆ្នាំថ្មីប្រពៃណីជាតិខ្មែរ! 🌸"
    }
    alert_text = "🧪 *[សារតេស្តសាកល្បង - Preview 4:00 AM Alert]*\n\n" + format_alert_message(sample_holiday)
    await send_clean_response(update, context, alert_text, reply_markup=get_back_keyboard(), parse_mode="Markdown")

async def ask_ai_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /ask command for AI consultation."""
    user_query = " ".join(context.args) if context.args else ""
    if not user_query:
        await safe_reply_text(
            update.message,
            "💡 *របៀបសួរ AI:*\nសូមវាយ `/ask <សំណួររបស់អ្នក>`\n\nឧទាហរណ៍៖ `/ask តើថ្ងៃចូលឆ្នាំខ្មែរមានប្រវត្តិយ៉ាងណា?`"
        )
        return
        
    await update.message.chat.send_action("typing")
    status = await update.message.reply_text("✨ *AI កំពុងគិត និងស្វែងរកចម្លើយ...* 🤖", parse_mode="Markdown")
    try:
        response_text = await query_ai(user_query)
        await safe_edit_text(status, response_text)
    except Exception as e:
        logger.error(f"Error in ask_ai_command: {e}")
        await safe_edit_text(status, f"❌ AI Error: {str(e)[:120]}")

# -------------------------------------------------------------
# Callback Query Handler
# -------------------------------------------------------------
async def button_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle inline button clicks."""
    query = update.callback_query
    data = query.data
    chat_id = query.message.chat_id
    user = query.from_user

    # Delegate media download callbacks (MP3 & HD Cover)
    if data.startswith("dlmp3_") or data.startswith("dlthumb_"):
        from handlers.video_handlers import handle_media_download_callback
        handled = await handle_media_download_callback(update, context)
        if handled:
            return
    
    try:
        if data == "btn_upcoming":
            await query.answer()
            msg = format_upcoming_message()
            await query.edit_message_text(msg, reply_markup=get_back_keyboard(), parse_mode="Markdown")
            
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
                [InlineKeyboardButton("🔙 ត្រឡប់ទៅ Menu ដើម", callback_data="btn_back_main")]
            ]
            await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
            
        elif data == "btn_finance":
            await query.answer("កំពុងទាញយកទិន្នន័យសេដ្ឋកិច្ច...")
            report = await format_finance_report()
            await query.edit_message_text(
                report,
                reply_markup=InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton("🔄 ធ្វើបច្ចុប្បន្នភាព", callback_data="btn_finance"),
                        InlineKeyboardButton("🔙 Menu ដើម", callback_data="btn_back_main")
                    ]
                ]),
                parse_mode="Markdown"
            )

        elif data == "btn_budget":
            await query.answer("កំពុងរៀបចំរបាយការណ៍ចំណូល-ចំណាយ...")
            rep = format_budget_report(chat_id, days=30)
            await query.edit_message_text(
                rep,
                reply_markup=InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton("🔄 ធ្វើបច្ចុប្បន្នភាព", callback_data="btn_budget"),
                        InlineKeyboardButton("🗑️ សម្អាតប្រវត្តិ", callback_data="btn_clear_expenses_ask")
                    ],
                    [InlineKeyboardButton("🔙 Menu ដើម", callback_data="btn_back_main")]
                ]),
                parse_mode="Markdown"
            )

        elif data == "btn_clear_expenses_ask":
            await query.answer()
            confirm_kb = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("⚠️ បាទ/ចាស! លុបទាំងអស់", callback_data="btn_clear_expenses_confirm"),
                    InlineKeyboardButton("❌ ទេ! ត្រឡប់ក្រោយ", callback_data="btn_budget")
                ]
            ])
            await query.edit_message_text(
                "⚠️ *តើអ្នកពិតជាចង់លុបប្រវត្តិកត់ត្រាចំណូល-ចំណាយទាំងអស់មែនទេ?*\n\n"
                "_ទិន្នន័យដែលលុបហើយមិនអាចយកមកវិញបានឡើយ!_",
                reply_markup=confirm_kb,
                parse_mode="Markdown"
            )

        elif data == "btn_clear_expenses_confirm":
            count = clear_user_expenses(chat_id)
            await query.answer(f"✅ បានលុបកំណត់ត្រាចំនួន {count} រួចរាល់!", show_alert=True)
            rep = format_budget_report(chat_id, days=30)
            await query.edit_message_text(
                rep,
                reply_markup=get_back_keyboard(),
                parse_mode="Markdown"
            )

        elif data == "btn_news":
            await query.answer("កំពុងទាញយកព័ត៌មានជាតិ & បច្ចេកវិទ្យា...")
            news_rep = await generate_morning_news_digest()
            await query.edit_message_text(
                news_rep,
                reply_markup=InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton("🔄 ធ្វើបច្ចុប្បន្នភាព", callback_data="btn_news"),
                        InlineKeyboardButton("🔙 Menu ដើម", callback_data="btn_back_main")
                    ]
                ]),
                parse_mode="Markdown"
            )

        elif data == "btn_music_help":
            await query.answer()
            m_help = (
                "🎧 *ស្វែងរក និងទាញយកចម្រៀង MP3 320kbps៖*\n\n"
                "• វាយពាក្យបញ្ជា៖ `/song <ឈ្មោះបទ ឬតារាចម្រៀង>`\n"
                "• ឧទាហរណ៍៖ `/song ស្រលាញ់គ្នាម្តងទៀតបានទេ`\n"
                "• ឧទាហរណ៍៖ `/song shape of you`\n\n"
                "🔍 *ស្វែងរកប្រភពបទភ្លេង TikTok (Sound Identifier)៖*\n"
                "• វាយ៖ `/sound <Link វីដេអូ TikTok>`\n\n"
                "Bot នឹងទាញយក file MP3 កម្រិតច្បាស់ ព្រមទាំងរូប Cover Album ជូនភ្លាមៗ!"
            )
            await query.edit_message_text(m_help, reply_markup=get_back_keyboard(), parse_mode="Markdown")
            
        elif data == "btn_toggle_aimode":
            current = is_ai_mode(chat_id)
            new_state = not current
            set_ai_mode(chat_id, new_state)
            ans_text = "🤖 បានបើក AI Continuous Chat Mode!" if new_state else "🔕 បានបិទ AI Continuous Chat Mode!"
            await query.answer(ans_text, show_alert=True)
            await query.edit_message_reply_markup(reply_markup=get_main_menu_keyboard(chat_id))

        elif data == "btn_reminders":
            await query.answer()
            rems = get_user_reminders(chat_id)
            if not rems:
                await query.edit_message_text(
                    "⏰ *អ្នកពុំទាន់មានសារដាស់តឿននៅឡើយទេ។*\n\n"
                    "ដើម្បីកំណត់ដាស់តឿន សូមវាយ៖\n`/remind <ម៉ោង> <កិច្ចការ>` ឧ. `/remind 08:30 ជួបភ្ញៀវ`",
                    reply_markup=get_back_keyboard(),
                    parse_mode="Markdown"
                )
            else:
                lines = ["⏰ *បញ្ជីសារដាស់តឿនរបស់អ្នក (Active Reminders)៖*\n"]
                buttons = []
                for r in rems:
                    lines.append(f"• 🕒 *`{r['time_str']}`*: {r['message']}")
                    buttons.append([InlineKeyboardButton(f"❌ លុប: {r['message'][:20]}", callback_data=f"delrem_{r['id']}")])
                buttons.append([InlineKeyboardButton("🔙 Menu ដើម", callback_data="btn_back_main")])
                await query.edit_message_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(buttons), parse_mode="Markdown")

        elif data.startswith("delrem_"):
            rem_id = int(data.replace("delrem_", ""))
            delete_reminder(rem_id, chat_id)
            await query.answer("✅ បានលុបសារដាស់តឿនរួចរាល់!", show_alert=True)
            # Re-render reminders list
            rems = get_user_reminders(chat_id)
            if not rems:
                await query.edit_message_text(
                    "⏰ *ពុំមានសារដាស់តឿនសេសសល់ឡើយ។*",
                    reply_markup=get_back_keyboard(),
                    parse_mode="Markdown"
                )
            else:
                lines = ["⏰ *បញ្ជីសារដាស់តឿនរបស់អ្នក (Active Reminders)៖*\n"]
                buttons = []
                for r in rems:
                    lines.append(f"• 🕒 *`{r['time_str']}`*: {r['message']}")
                    buttons.append([InlineKeyboardButton(f"❌ លុប: {r['message'][:20]}", callback_data=f"delrem_{r['id']}")])
                buttons.append([InlineKeyboardButton("🔙 Menu ដើម", callback_data="btn_back_main")])
                await query.edit_message_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(buttons), parse_mode="Markdown")

        elif data == "btn_tools_menu":
            await query.answer()
            tools_msg = (
                "🛠️ *មជ្ឈមណ្ឌលឧបករណ៍ប្រើប្រាស់ (Utility Tools Hub)*\n\n"
                "🔲 *១. បង្កើត QR Code៖*\n"
                "• វាយ `/qr <អត្ថបទ ឬ Link>`\n"
                "• ឧ. `/qr https://t.me/Researchmap_bot`\n\n"
                "📷 *២. អាន QR Code & KHQR ធនាគារ៖*\n"
                "• ផ្ញើរូបភាព QR Code ឬ KHQR ចូលក្នុង Bot នេះភ្លាមៗ\n"
                "• Bot នឹងទាញយកទិន្នន័យពីក្នុងរូបភាពនោះជូន\n\n"
                "🎙️ *៣. ជជែកជាសំឡេង (Voice AI)៖*\n"
                "• គ្រាន់តែសង្កត់ផ្ញើសារសំឡេង Voice Note នោះ AI នឹងឆ្លើយតបមកវិញ\n\n"
                "📄 *៤. Vision AI & OCR៖*\n"
                "• ផ្ញើរូបភាពឯកសារ វិក្កយបត្រ ឬលំហាត់ ➔ AI ជួយអាន និងដោះស្រាយ"
            )
            await query.edit_message_text(tools_msg, reply_markup=get_back_keyboard(), parse_mode="Markdown")

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
                    [InlineKeyboardButton("🔙 ត្រឡប់ទៅ Menu ដើម", callback_data="btn_back_main")]
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
            await query.edit_message_text(text, reply_markup=get_location_selection_keyboard(), parse_mode="Markdown")
            
        elif data.startswith("setloc_"):
            prov_key = data.replace("setloc_", "")
            prov_info = PROVINCE_PRESETS.get(prov_key)
            if prov_info:
                set_user_location(chat_id, prov_info["lat"], prov_info["lon"], prov_info["name"])
                set_weather_alert_active(chat_id, True)
                await query.answer(f"✅ បានកំណត់ទីតាំង៖ {prov_info['name']}!", show_alert=True)
                
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
                msg = "🧪 *[សារតេស្តសាកល្បង - 5:00 AM Weather Alert]*\n\n" + format_weather_message(w_data, loc_name, is_daily_alert=True)
            else:
                msg = "❌ មិនអាចទាញយកព័ត៌មានអាកាសធាតុបានទេ។"
                
            await query.edit_message_text(msg, reply_markup=get_back_keyboard(), parse_mode="Markdown")

        elif data == "btn_status":
            await query.answer()
            subscribed = is_subscribed(chat_id)
            today_holiday = get_today_holiday()
            today_date = get_current_cambodia_date()
            w_settings = get_user_weather_settings(chat_id)
            loc_name = w_settings.get("location_name", "ភ្នំពេញ")
            weather_active = w_settings.get("is_active", True)
            ai_active = is_ai_mode(chat_id)
            rems = get_user_reminders(chat_id)
            first_name = user.full_name if user else "អ្នកប្រើប្រាស់"
            
            status_text = (
                "📊 *ស្ថានភាពគណនីរបស់អ្នក (Account Status)*\n\n"
                f"👤 ឈ្មោះ: *{first_name}*\n"
                f"🆔 Telegram ID: `{chat_id}`\n"
                f"📅 កាលបរិច្ឆេទ: `{today_date}` (Asia/Phnom_Penh)\n"
                f"📍 ទីតាំងអាកាសធាតុ: *{loc_name}*\n"
                f"🌅 ដំណឹងអាកាសធាតុ ៥:០០ ព្រឹក: {'✅ កំពុងបើក (Active)' if weather_active else '❌ បានបិទ (Inactive)'}\n"
                f"🔔 ដំណឹងបុណ្យជាតិ ៤:០០ ព្រឹក: {'✅ កំពុងបើក (Active)' if subscribed else '❌ បានបិទ (Inactive)'}\n"
                f"💬 AI Continuous Chat: {'✅ កំពុងបើក (Active)' if ai_active else '❌ បានបិទ (Inactive)'}\n"
                f"⏰ Reminders កំពុងរង់ចាំ: *{len(rems)}* កិច្ចការ\n"
                f"🎉 ថ្ងៃឈប់សម្រាកថ្ងៃនេះ: {today_holiday['name_km'] if today_holiday else 'ពុំមែនជាថ្ងៃឈប់សម្រាកទេ'}\n"
            )
            await query.edit_message_text(status_text, reply_markup=get_back_keyboard(), parse_mode="Markdown")
            
        elif data == "btn_subscribe":
            add_subscriber(chat_id, user.username if user else None, query.message.chat.type)
            await query.answer("✅ បានបើកការដាស់តឿនបុណ្យជាតិ ៤:០០ ព្រឹកជោគជ័យ!", show_alert=True)
            await query.edit_message_reply_markup(reply_markup=get_main_menu_keyboard(chat_id))
            
        elif data == "btn_unsubscribe":
            remove_subscriber(chat_id)
            await query.answer("🔕 បានបិទការដាស់តឿនបុណ្យជាតិ ៤:០០ ព្រឹក!", show_alert=True)
            await query.edit_message_reply_markup(reply_markup=get_main_menu_keyboard(chat_id))
            
        elif data == "btn_video_help":
            await query.answer()
            help_msg = (
                "📥 *របៀបទាញយកវីដេអូ & MP3 & Cover HD៖*\n\n"
                "1. ចូលទៅកាន់ TikTok, YouTube, Facebook, Instagram ឬ X/Twitter\n"
                "2. ចុចពាក្យ **Share** រួចជ្រើសរើស **Copy Link**\n"
                "3. ផ្ញើ (Paste) Link ចូលក្នុង Bot នេះភ្លាមៗ\n"
                "4. Bot នឹងទាញយកវីដេអូ HD ជូនអ្នក និងមានប៊ូតុងសម្រាប់ទាញយក **MP3** ឬ **Cover HD** ដោយស្វ័យប្រវត្ត!"
            )
            await query.edit_message_text(help_msg, reply_markup=get_back_keyboard(), parse_mode="Markdown")
            
        elif data == "btn_ai_menu":
            await query.answer()
            ai_active = is_ai_mode(chat_id)
            ai_msg = (
                "✨ *ជំនួយការឆ្លាតវៃ AI (Gemini 2.5 Flash & GPT)* 🤖\n\n"
                "លោកអ្នកអាចសួរនាំសំណួរ វិភាគទិន្នន័យ បកប្រែភាសា និងសរសេរអត្ថបទបានយ៉ាងរហ័ស!\n\n"
                "💡 *មុខងារពិសេសៗ៖*\n"
                f"• **AI Continuous Chat:** {'✅ កំពុងបើក' if ai_active else '❌ បានបិទ'} (ជជែកជាប់គ្នាដោយមិនបាច់វាយ /ask)\n"
                "• **Voice Message AI:** ផ្ញើសារសំឡេង Voice ➔ AI ឆ្លើយតបជាសំឡេង/អក្សរ\n"
                "• **Vision OCR:** ផ្ញើរូបភាព ➔ AI អានអក្សរ បកប្រែ ឬដោះស្រាយលំហាត់\n"
                "• **Command:** `/ask <សំណួរ>`"
            )
            keyboard = [
                [InlineKeyboardButton("💬 បើក/បិទ AI Continuous Chat", callback_data="btn_toggle_aimode")],
                [InlineKeyboardButton("🗑️ សម្អាត Conversation Memory", callback_data="btn_clear_aimem")],
                [InlineKeyboardButton("🔙 Menu ដើម", callback_data="btn_back_main")]
            ]
            await query.edit_message_text(ai_msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

        elif data == "btn_clear_aimem":
            clear_chat_history(chat_id)
            await query.answer("✅ បានសម្អាតការចងចាំ AI រួចរាល់!", show_alert=True)

        elif data == "btn_help":
            await query.answer()
            help_msg = (
                "💡 *មជ្ឈមណ្ឌលជំនួយ និងការណែនាំ (Help Hub)*\n\n"
                "📥 *១. ការទាញយកវីដេអូ (Video Downloader):*\n"
                "• គាំទ្រ: TikTok (No Watermark), YouTube Shorts/Videos, Facebook, Instagram, X/Twitter\n"
                "• គាំទ្រការទាញយក MP3, Cover HD និង Quality Selector\n\n"
                "💰 *២. សេដ្ឋកិច្ច និងហិរញ្ញវត្ថុ:*\n"
                "• អត្រាប្តូរប្រាក់ (NBC/USD/KHR/THB/EUR/CNY), តម្លៃមាស, តម្លៃប្រេងឥន្ធនៈ\n\n"
                "⏰ *៣. សារដាស់តឿន (Reminders):*\n"
                "• កំណត់តាមម៉ោងផ្ទាល់ខ្លួន `/remind 08:30 ជួបភ្ញៀវ` ឬ `/remind 15m ហូបថ្នាំ`\n\n"
                "🤖 *៤. AI ឆ្លាតវៃ:*\n"
                "• Voice Messages, Vision OCR, Continuous AI Chat Mode (`/aimode`)\n\n"
                "🌤️ *៥. ដំណឹងអាកាសធាតុ ៥:០០ ព្រឹក & បុណ្យជាតិ ៤:០០ ព្រឹក:*\n"
                "• ផ្ញើស្វ័យប្រវត្តតាមកាលវិភាគជាក់លាក់"
            )
            await query.edit_message_text(help_msg, reply_markup=get_back_keyboard(), parse_mode="Markdown")
            
        elif data == "btn_photo_loc_help":
            await query.answer()
            msg = (
                "📍 *របៀបទាញយកទីតាំង GPS ពីរូបភាព (Photo Location Extraction)៖*\n\n"
                "1. **ទាញយក GPS សុក្រឹត ១០០% ពីទូរស័ព្ទដៃ៖**\n"
                "   • ចុចផ្ញើរូបភាពដោយជ្រើសរើស **File / Document (Uncompressed)** មកកាន់ Bot\n"
                "   • Bot នឹងអាន EXIF GPS Metadata ពីកាមេរ៉ា ហើយទាញយកឈ្មោះភូមិ ឃុំ ស្រុក ខេត្ត និងផ្ញើ Pin លើ Google Maps ជូនភ្លាមៗ!\n\n"
                "2. **ស្វែងរកទីតាំងតាមរូបភាព (AI Geolocation)៖**\n"
                "   • ផ្ញើរូបភាពធម្មតាដោយដាក់ Caption ថា `ទីតាំង` ឬ `កន្លែងណា` ឬ `/location`\n"
                "   • AI នឹងពិនិត្យមើលវត្តអារាម សំណង់ប្រវត្តិសាស្ត្រ ស្លាកសញ្ញា ឬផ្លូវ ដើម្បីកំណត់ទីតាំងជូន!"
            )
            await query.message.reply_text(msg, parse_mode="Markdown")

        elif data == "btn_photo_enhance_help":
            await query.answer()
            msg = (
                "🔍 *របៀបធ្វើឱ្យរូបភាពកាន់តែច្បាស់ (AI Image Enhancer)៖*\n\n"
                "👉 ចុច **Reply** លើរូបភាពណាមួយ រួចវាយ `/enhance` ឬ `/upscale`\n"
                "👉 ឬផ្ញើរូបភាពថ្មីដោយដាក់ Caption ថា `/enhance`\n\n"
                "Bot នឹងជួយសម្អាត Noise, ពង្រីកទំហំ 2x-4x និងធ្វើឱ្យរូបភាពកាន់តែច្បាស់ភ្លាមៗ! ✨"
            )
            await query.message.reply_text(msg, parse_mode="Markdown")

        elif data == "btn_photo_watermark_help":
            await query.answer()
            msg = (
                "💧 *របៀបបោះត្រា Watermark ការពាររូបភាពផលិតផល៖*\n\n"
                "👉 ចុច **Reply** លើរូបភាពណាមួយ រួចវាយ `/watermark <ឈ្មោះហាង លេខទូរស័ព្ទ>`\n"
                "👉 ឧទាហរណ៍៖ `/watermark ហាង ពិសិដ្ឋ 012 345 678`\n\n"
                "Bot នឹងបោះត្រាស្អាតៗកម្រិត Professional ការពារគេលួចចម្លងរូបភាព! 🛡️"
            )
            await query.message.reply_text(msg, parse_mode="Markdown")

        elif data == "btn_photo_rembg_help":
            await query.answer()
            msg = (
                "✂️ *របៀបកាត់ផ្ទៃខាងក្រោយរូបភាព (AI Background Remover)៖*\n\n"
                "👉 ចុច **Reply** លើរូបភាពណាមួយ រួចវាយ `/rembg`\n"
                "Bot នឹងកាត់ចេញ background ក្លាយជា Transparent PNG ក្នុងរយៈពេល ៣ វិនាទី!"
            )
            await query.message.reply_text(msg, parse_mode="Markdown")

        elif data == "btn_pdf_help":
            await query.answer()
            msg = (
                "📄 *ជំនួយការឯកសារ PDF & Chat with PDF (/pdf)* 🇰🇭\n\n"
                "👉 *របៀបប្រើប្រាស់ងាយៗ៖*\n"
                "1. **ផ្ញើ ឬ Forward File PDF ចូលមកកាន់ Bot** (កិច្ចសន្យា, សៀវភៅ, មេរៀន, ឬរបាយការណ៍)\n"
                "2. Bot នឹងអាន និងសង្ខេបចំណុចសំខាន់ៗជាភាសាខ្មែរភ្លាមៗ\n"
                "3. បន្ទាប់មក បងអាច **Reply លើសារសង្ខេប** ឬវាយ `/pdf <សំណួរ>` ដើម្បីសួរលម្អិតពីទំព័រណាមួយបាន!"
            )
            await query.edit_message_text(msg, reply_markup=get_back_keyboard(), parse_mode="Markdown")

        elif data == "btn_back_main":
            await query.answer()
            first_name = user.first_name if user else "លោកអ្នក"
            await query.edit_message_text(
                get_welcome_text(first_name),
                reply_markup=get_main_menu_keyboard(chat_id),
                parse_mode="Markdown"
            )

        elif data == "btn_clean_chat":
            await query.answer("🧹 កំពុងសម្អាតសារចាស់ៗ...")
            current_msg_id = query.message.message_id if query.message else None
            
            # Delete the message containing the button first
            try:
                await query.message.delete()
            except Exception:
                pass
                
            if current_msg_id:
                start_id = max(1, current_msg_id - 40)
                msg_ids = list(range(start_id, current_msg_id))
                try:
                    for i in range(0, len(msg_ids), 100):
                        chunk = msg_ids[i:i+100]
                        await context.bot.delete_messages(chat_id=chat_id, message_ids=chunk)
                except Exception:
                    for mid in reversed(msg_ids):
                        try:
                            await context.bot.delete_message(chat_id=chat_id, message_id=mid)
                        except Exception:
                            pass
                            
            context.user_data.pop("last_remind_msg_id", None)
            context.user_data.pop("last_menu_id", None)

            clean_notice = (
                f"🧹 *បានសម្អាតសារចាស់ៗដោយជោគជ័យ!* ✨\n\n"
                f"ឥឡូវនេះការជជែករបស់អ្នកមានសភាពស្អាតបាត និងគ្មានសារចាស់ៗកកកុញទៀតឡើយ។\n"
                f"សូមជ្រើសរើសមុខងារដែលចង់ប្រើប្រាស់បន្តខាងក្រោម៖"
            )
            sent_menu = await context.bot.send_message(
                chat_id=chat_id,
                text=clean_notice,
                reply_markup=get_main_menu_keyboard(chat_id),
                parse_mode="Markdown"
            )
            context.user_data["last_menu_id"] = sent_menu.message_id

        elif data == "btn_delete_this_msg":
            try:
                await query.message.delete()
                await query.answer("🗑️ បានលុបសារនេះរួចរាល់")
            except Exception:
                await query.answer()
    except Exception as e:
        logger.warning(f"Callback error: {e}")
        try:
            await query.answer()
        except Exception:
            pass
