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
        "🎞️ *២. គុណភាព & Cover:* ទាញយក MP3, Cover HD ឬជ្រើសរើស Resolution (1080p, 720p, 480p)\n"
        "💰 *៣. សេដ្ឋកិច្ចកម្ពុជា:* អត្រាប្តូរប្រាក់ NBC/USD/KHR, តម្លៃមាស (តម្លឹង/ជី), តម្លៃប្រេងឥន្ធនៈ\n"
        "🤖 *៤. AI ឆ្លាតវៃ:* ជជែកជាសំឡេង (Voice AI), អានរូបភាព/ឯកសារ/ដោះស្រាយលំហាត់ (Vision OCR), Continuous Chat Mode\n"
        "🔔 *៥. សារដាស់តឿន:* កំណត់ម៉ោងរំលឹកកិច្ចការ `/remind 08:30 ជួបភ្ញៀវ`\n"
        "🔲 *៦. ឧបករណ៍ QR:* បង្កើត/អាន QR Code និង KHQR\n"
        "🌤️ *៧. អាកាសធាតុ ៥:០០ ព្រឹក:* ផ្ញើតាមទីតាំងជាក់ស្តែងរាល់ព្រឹក\n"
        "🗓️ *៨. ប្រតិទិនបុណ្យជាតិ ៤:០០ ព្រឹក:* ជូនដំណឹងទៀបភ្លឺរាល់ថ្ងៃបុណ្យជាតិ\n\n"
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
            InlineKeyboardButton("💰 សេដ្ឋកិច្ច / មាស / សាំង", callback_data="btn_finance"),
        ],
        [
            InlineKeyboardButton("🗓️ ប្រតិទិនបុណ្យជាតិ", callback_data="btn_calendar_2026"),
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
            InlineKeyboardButton("🛠️ ឧបករណ៍ QR / KHQR", callback_data="btn_tools_menu"),
            InlineKeyboardButton("📊 ស្ថានភាពគណនី", callback_data="btn_status"),
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
        [KeyboardButton("💰 សេដ្ឋកិច្ច/មាស/សាំង"), KeyboardButton("🌤️ អាកាសធាតុ")],
        [KeyboardButton("📍 ផ្ញើទីតាំង GPS", request_location=True), KeyboardButton("⏰ Reminders")],
        [KeyboardButton("📥 របៀបទាញយក"), KeyboardButton("🗓️ ប្រតិទិនបុណ្យជាតិ")],
        [KeyboardButton("✨ AI Chat"), KeyboardButton("🏠 ផ្ទាំង Menu មេ")]
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
# Command Handlers
# -------------------------------------------------------------
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command with auto-cleanup and persistent keyboard."""
    chat = update.effective_chat
    user = update.effective_user
    
    add_subscriber(chat.id, user.username if user else None, chat.type)
    
    prev_menu_id = context.user_data.get("last_menu_id")
    if prev_menu_id:
        try:
            await context.bot.delete_message(chat_id=chat.id, message_id=prev_menu_id)
        except Exception:
            pass
            
    if chat.type == "private":
        try:
            await update.message.delete()
        except Exception:
            pass
        
    first_name = user.first_name if user else "មិត្តសំឡាញ់"
    sent_msg = await context.bot.send_message(
        chat_id=chat.id,
        text=get_welcome_text(first_name),
        reply_markup=get_main_menu_keyboard(chat.id),
        parse_mode="Markdown"
    )
    context.user_data["last_menu_id"] = sent_msg.message_id
    
    if chat.type == "private":
        try:
            await context.bot.send_message(
                chat_id=chat.id,
                text="📱 _ចុច Menu ឬប៊ូតុងខាងក្រោមសម្រាប់បញ្ជា Bot:_ ",
                reply_markup=get_persistent_bottom_keyboard(),
                parse_mode="Markdown"
            )
        except Exception:
            pass

async def finance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /finance command to view exchange rates, gold, and fuel prices."""
    await update.message.chat.send_action("typing")
    report = await format_finance_report()
    await update.message.reply_text(
        report,
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🔄 ធ្វើបច្ចុប្បន្នភាព", callback_data="btn_finance"),
                InlineKeyboardButton("🔙 Menu ដើម", callback_data="btn_back_main")
            ]
        ]),
        parse_mode="Markdown"
    )

async def convert_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /convert <amount> <from> <to> command."""
    args = context.args or []
    if len(args) < 3:
        await update.message.reply_text(
            "💱 *របៀបប្រើប្រាស់ការប្តូររូបិយប័ណ្ណ៖*\n\n"
            "សូមវាយ៖ `/convert <ចំនួនទឹកប្រាក់> <ពី> <ទៅ>`\n\n"
            "• ឧទាហរណ៍៖ `/convert 100 USD KHR`\n"
            "• ឧទាហរណ៍៖ `/convert 400000 KHR USD`\n"
            "• ឧទាហរណ៍៖ `/convert 1000 THB KHR`",
            parse_mode="Markdown"
        )
        return
        
    try:
        amount = float(args[0].replace(",", ""))
        from_c = args[1]
        to_c = args[2]
        res = await convert_currency_text(amount, from_c, to_c)
        await update.message.reply_text(res, parse_mode="Markdown")
    except ValueError:
        await update.message.reply_text("❌ ចំនួនទឹកប្រាក់មិនត្រឹមត្រូវ។ សូមបញ្ចូលលេខជាក់ស្តែង ឧ. `/convert 50 USD KHR`", parse_mode="Markdown")

async def remind_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /remind <time> <message> command."""
    text = " ".join(context.args) if context.args else ""
    if not text:
        await update.message.reply_text(
            "⏰ *របៀបកំណត់សារដាស់តឿន (Custom Reminders)៖*\n\n"
            "សូមវាយ៖ `/remind <ម៉ោង> <កិច្ចការដែលត្រូវធ្វើ>`\n\n"
            "👉 *ឧទាហរណ៍ម៉ោងជាក់លាក់៖*\n"
            "• `/remind 08:30 ត្រូវទៅជួបភ្ញៀវនៅហាងកាហ្វេ`\n"
            "• `/remind 21:00 លេបថ្នាំ និងចូលគេង`\n\n"
            "👉 *ឧទាហរណ៍កំណត់តាមនាទី/ម៉ោងបន្ទាប់៖*\n"
            "• `/remind 15m ឆុងកាហ្វេ និងពិនិត្យ Email`\n"
            "• `/remind 2h បញ្ចប់របាយការណ៍ការងារ`",
            parse_mode="Markdown"
        )
        return
        
    parsed = parse_reminder_input(text)
    if not parsed:
        await update.message.reply_text(
            "❌ *ទម្រង់ម៉ោងមិនត្រឹមត្រូវ!*\n\n"
            "សូមបញ្ជាក់ម៉ោងដូចជា៖ `08:30`, `14:00`, `15m`, ឬ `2h` រួមជាមួយអត្ថបទកិច្ចការ។",
            parse_mode="Markdown"
        )
        return
        
    remind_at, time_str, message_body = parsed
    chat_id = update.effective_chat.id
    rem_id = add_reminder(chat_id, remind_at, time_str, message_body)
    
    await update.message.reply_text(
        f"✅ *បានកត់ត្រាសារដាស់តឿនជោគជ័យ!* ⏰\n\n"
        f"🕒 *ម៉ោងរំលឹក៖* `{time_str}` (ម៉ោងនៅកម្ពុជា)\n"
        f"📝 *កិច្ចការ៖* {message_body}\n\n"
        f"🔔 Bot នឹងផ្ញើសាររំលឹកអ្នកចំពេលនេះដោយស្វ័យប្រវត្ត!",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📋 មើលបញ្ជី Reminders ទាំងអស់", callback_data="btn_reminders")]
        ]),
        parse_mode="Markdown"
    )

async def reminders_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /reminders command to list user's reminders."""
    chat_id = update.effective_chat.id
    rems = get_user_reminders(chat_id)
    if not rems:
        await update.message.reply_text(
            "⏰ *អ្នកពុំទាន់មានសារដាស់តឿននៅឡើយទេ។*\n\n"
            "ដើម្បីកំណត់ដាស់តឿន សូមវាយ៖\n`/remind <ម៉ោង> <កិច្ចការ>` ឧទាហរណ៍ `/remind 08:30 ជួបភ្ញៀវ`",
            reply_markup=get_back_keyboard(),
            parse_mode="Markdown"
        )
        return
        
    lines = ["⏰ *បញ្ជីសារដាស់តឿនរបស់អ្នក (Active Reminders)៖*\n"]
    buttons = []
    for r in rems:
        lines.append(f"• 🕒 *`{r['time_str']}`*: {r['message']}")
        buttons.append([InlineKeyboardButton(f"❌ លុប: {r['message'][:25]}", callback_data=f"delrem_{r['id']}")])
        
    buttons.append([InlineKeyboardButton("🔙 Menu ដើម", callback_data="btn_back_main")])
    await update.message.reply_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(buttons),
        parse_mode="Markdown"
    )

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
        
    await update.message.reply_text(
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
        await update.message.reply_photo(
            photo=bio,
            caption=f"🔲 *QR Code របស់អ្នកត្រូវបានបង្កើតជោគជ័យ!* ✨\n\n📝 ទិន្នន័យ៖ `{text[:100]}`",
            parse_mode="Markdown"
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
        await status.edit_text(reply_text, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Error handling voice message: {e}")
        await status.edit_text(f"❌ មិនអាចដំណើរការសារជាសំឡេងបានទេ៖ {str(e)[:100]}")

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
            await update.message.reply_text(
                msg,
                reply_markup=InlineKeyboardMarkup(buttons),
                parse_mode="Markdown"
            )
            return
            
        # 2. Otherwise process with Gemini Vision OCR / AI
        status = await update.message.reply_text("📷 *AI កំពុងអាន និងវិភាគរូបភាពរបស់អ្នក...* 🔍", parse_mode="Markdown")
        reply_text = await process_vision_ai(img_bytes, mime_type="image/jpeg", caption=caption)
        await status.edit_text(reply_text, parse_mode="Markdown")
        
    except Exception as e:
        logger.error(f"Error handling photo: {e}")
        await update.message.reply_text(f"❌ កំហុសក្នុងការដំណើរការរូបភាព៖ {str(e)[:100]}")

# -------------------------------------------------------------
# Existing Weather, Calendar & Alert Commands
# -------------------------------------------------------------
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
        "💡 *បញ្ជី Command ពេញលេញសម្រាប់ប្រើប្រាស់៖*\n\n"
        "🔹 `/start` - បើកផ្ទាំង Dashboard មេ\n"
        "🔹 `/finance` - មើលអត្រាប្តូរប្រាក់ តម្លៃមាស និងតម្លៃសាំង\n"
        "🔹 `/convert 100 USD KHR` - គណនាប្តូរប្រាក់រហ័ស\n"
        "🔹 `/remind 08:30 ជួបភ្ញៀវ` - កំណត់ម៉ោងរំលឹកកិច្ចការ\n"
        "🔹 `/reminders` - មើលបញ្ជីសារដាស់តឿនរបស់អ្នក\n"
        "🔹 `/aimode` - បើក/បិទ AI Continuous Chat Mode\n"
        "🔹 `/ask <សំណួរ>` - សួរសំណួរទៅ AI (Gemini/GPT)\n"
        "🔹 `/qr <link/text>` - បង្កើត QR Code ភ្លាមៗ\n"
        "🔹 `/weather` - មើលអាកាសធាតុបច្ចុប្បន្ន\n"
        "🔹 `/location` - កំណត់ទីតាំងអាកាសធាតុ 5AM\n"
        "🔹 `/upcoming` - មើលថ្ងៃបុណ្យដែលខិតជិតមកដល់\n"
        "🔹 `/calendar` - មើលប្រតិទិនឈប់សម្រាកប្រចាំឆ្នាំ\n"
        "🔹 `/subscribe` - បើកដំណឹងបុណ្យជាតិ ៤:០០ ព្រឹក\n"
        "🔹 `/unsubscribe` - បិទដំណឹងបុណ្យជាតិ\n"
        "🔹 `/status` - ពិនិត្យស្ថានភាពគណនី\n\n"
        "🎙️ *Voice AI:* សង្កត់ផ្ញើសារសំឡេងដើម្បីជជែកជាមួយ AI\n"
        "📷 *Vision OCR:* ផ្ញើរូបភាពដើម្បីអានអក្សរ QR/KHQR ឬដោះស្រាយលំហាត់\n"
        "📥 *Video:* Copy Link (TikTok/YouTube/FB) ផ្ញើចូលទីនេះភ្លាមៗ!"
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
        [InlineKeyboardButton("🔙 ត្រឡប់ទៅ Menu ដើម", callback_data="btn_back_main")]
    ]
    msg = format_calendar_message(current_year)
    await update.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def subscribe_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /subscribe command."""
    chat = update.effective_chat
    user = update.effective_user
    add_subscriber(chat.id, user.username if user else None, chat.type)
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
    await update.message.reply_text(status_text, reply_markup=get_back_keyboard(), parse_mode="Markdown")

async def test_alert_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /test_alert command."""
    upcoming = get_upcoming_holidays(limit=1)
    sample_holiday = upcoming[0] if upcoming else {
        "date": "2026-04-14",
        "name_km": "ពិធីបុណ្យចូលឆ្នាំថ្មីប្រពៃណីជាតិ",
        "name_en": "Khmer New Year",
        "wishes": "សួស្តីឆ្នាំថ្មីប្រពៃណីជាតិខ្មែរ! 🌸"
    }
    alert_text = "🧪 *[សារតេស្តសាកល្បង - Preview 4:00 AM Alert]*\n\n" + format_alert_message(sample_holiday)
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
            
        elif data == "btn_back_main":
            await query.answer()
            first_name = user.first_name if user else "លោកអ្នក"
            await query.edit_message_text(
                get_welcome_text(first_name),
                reply_markup=get_main_menu_keyboard(chat_id),
                parse_mode="Markdown"
            )
    except Exception as e:
        logger.warning(f"Callback error: {e}")
        try:
            await query.answer()
        except Exception:
            pass
