import os
import re
import html
import io
import shutil
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
    WebAppInfo,
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
    get_user_persona,
    set_user_persona,
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
    extract_maps_url_from_vision_text,
)
from services.camroad_car_service import (
    CAMBODIA_ROUTES,
    match_destination,
    calculate_trip_details,
    format_trip_report,
    diagnose_car_dashboard,
)
from services.code_runner_service import (
    execute_python_code_sandboxed,
    format_execution_result,
    debug_and_explain_code,
)
from services.receipt_budget_service import (
    scan_receipt_image,
    record_receipt_transaction,
    generate_budget_pie_chart,
    generate_budget_excel,
)
from services.podcast_service import generate_article_podcast
from services.chord_music_service import find_song_chords, identify_song_from_audio
from services.user_resolver_service import (
    validate_username_format,
    resolve_telegram_user,
    format_user_resolver_card,
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

WEBAPP_URL = os.getenv("WEBAPP_URL", "https://assistant-bot-9ncu.onrender.com/app")

def get_welcome_text(user_first_name: str, chat_id: Optional[int] = None, page: int = 1) -> str:
    """Dynamic personalized welcome message based on selected persona or slider page."""
    persona = get_user_persona(chat_id) if chat_id else "all"

    if persona == "student":
        return (
            f"🎓 *មជ្ឈមណ្ឌលជំនួយការ - របៀបសិស្ស/និស្សិត (Student Mode)* ✨\n\n"
            f"👋 សួស្តី *{user_first_name}*! ផ្ទាំងនេះត្រូវបានរៀបចំពិសេសសម្រាប់ការសិក្សា & ស្រាវជ្រាវ៖\n\n"
            "📚 *១. ដោះស្រាយលំហាត់:* ផ្ញើរូបភាពលំហាត់ចូល Bot នឹងអាន & ដោះស្រាយជាជំហានៗ\n"
            "📄 *២. Chat with PDF:* ផ្ញើ File PDF សៀវភៅ ឬមេរៀន ដើម្បីសង្ខេប & សួរសំណួរ (`/pdf`)\n"
            "🌐 *៣. បកប្រែភាសា Pro:* បកប្រែ English ⬄ Khmer ជាមួយការបញ្ចេញសំឡេង (`/translate`)\n"
            "✍️ *៤. ពិនិត្យអក្ខរាវិរុទ្ធ:* កែតម្រូវពាក្យខុសតាមវចនានុក្រម សម្តេច ជួន ណាត (`/check`)\n"
            "📝 *៥. សង្ខេប YouTube AI:* ផ្ញើ Link មេរៀន YouTube ឬ Podcast សង្ខេបចំណុចសំខាន់ៗ (`/sum`)\n"
            "🎧 *៦. Web ➔ Audio Podcast:* បម្លែង Web Article ទៅជា Audio Podcast ស្តាប់កម្សាន្ត (`/listen`)\n"
            "💻 *៧. Code Sandbox:* សាកល្បង Run កូដ Python, JS, C++ និង AI Debugger (`/code`)\n\n"
            "👇 _ចុចប៊ូតុងខាងក្រោម ឬបើក Mini App ដើម្បីចាប់ផ្តើម៖_"
        )
    elif persona == "business":
        return (
            f"💼 *មជ្ឈមណ្ឌលជំនួយការ - របៀបអាជីវកម្ម & លក់ដូរ (Business Mode)* ✨\n\n"
            f"👋 សួស្តី *{user_first_name}*! ផ្ទាំងនេះត្រូវបានរៀបចំពិសេសសម្រាប់អាជីវកម្ម & ការគ្រប់គ្រង៖\n\n"
            "🧾 *១. ស្កេនវិក្កយបត្រ AI:* ថតរូបវិក្កយបត្រ ឬស្លីបធនាគារ ABA/Bakong កត់ចូលប្រព័ន្ធស្វ័យប្រវត្ត\n"
            "📊 *២. ចំណូល-ចំណាយ:* កត់ត្រាចំណាយ `/spend` និងទាញយក Excel / Donut Chart (`/budget`)\n"
            "💧 *៣. ការពាររូបទំនិញ:* វាយ `/watermark <ឈ្មោះហាង>` បោះត្រាការពារគេលួចចម្លង\n"
            "🛠️ *៤. KHQR & QR:* បង្កើត QR Code សម្រាប់ទទួលប្រាក់ ឬ Link អាជីវកម្ម (`/qr`)\n"
            "💵 *៥. សេដ្ឋកិច្ចកម្ពុជា:* អត្រាប្តូរប្រាក់ NBC, តម្លៃមាស, សាំង និងផ្សារ Crypto/TON (`/finance`)\n"
            "✂️ *៦. កាត់ Background:* កាត់ផ្ទៃខាងក្រោយរូបភាពទំនិញក្លាយជា Transparent PNG (`/rembg`)\n\n"
            "👇 _ចុចប៊ូតុងខាងក្រោម ឬបើក Mini App ដើម្បីចាប់ផ្តើម៖_"
        )
    elif persona == "creator":
        return (
            f"🎬 *មជ្ឈមណ្ឌលជំនួយការ - របៀបអ្នកកាត់ត & Media (Creator Mode)* ✨\n\n"
            f"👋 សួស្តី *{user_first_name}*! ផ្ទាំងនេះត្រូវបានរៀបចំពិសេសសម្រាប់អ្នកបង្កើតមាតិកា៖\n\n"
            "📥 *១. Video Downloader:* ទាញយកវីដេអូ 4K/8K គ្មាន Watermark (TikTok, FB, YT, IG, X)\n"
            "🎨 *២. AI Imagine:* បង្កើតរូបភាព Ultra HD តាមការពិពណ៌នាជាខ្មែរ (`/imagine`)\n"
            "✂️ *៣. Video Trimmer & GIF:* កាត់វីដេអូក្នុង Chat (`/trim`) & បម្លែងជា GIF (`/gif`)\n"
            "📑 *៤. Khmer Subtitles:* ទាញយក Subtitle ពី YouTube រួចបកប្រែជាខ្មែរ .SRT (`/sub`)\n"
            "🎧 *៥. YouTube Playlist:* ទាញយកចម្រៀងទាំងកញ្ចប់ចូល Channel @Song182 (`/playlist`)\n"
            "🌌 *៦. Super-Res 8K:* ពង្រីកគុណភាពរូបភាពដល់ 4K & 8K Super-Res (`/enhance 8k`)\n\n"
            "👇 _ចុចប៊ូតុងខាងក្រោម ឬបើក Mini App ដើម្បីចាប់ផ្តើម៖_"
        )
    else:
        page_titles = {
            1: "🌟 *ទំព័រ ១/៣៖ មុខងារពេញនិយម & AI Superpowers*",
            2: "💼 *ទំព័រ ២/៣៖ ហិរញ្ញវត្ថុ ការងារ & ផលិតភាព*",
            3: "🛠️ *ទំព័រ ៣/៣៖ ឧបករណ៍ប្រចាំថ្ងៃ ការពារ & ប្រព័ន្ធ*"
        }
        p_title = page_titles.get(page, page_titles[1])
        return (
            f"🌟 *មជ្ឈមណ្ឌលជំនួយការឆ្លាតវៃ (Smart Assistant Hub)* 🇰🇭\n\n"
            f"👋 សួស្តី *{user_first_name}*! {p_title}\n\n"
            "💡 _លោកអ្នកអាចចុច '📱 បើក Control Center' ដើម្បីប្រើផ្ទាំង App ទំនើប ឬចុចរំកិលទំព័រ [1/3] ⬅️ ➡️ ខាងក្រោម៖_"
        )

def get_main_menu_keyboard(chat_id: int, page: int = 1) -> InlineKeyboardMarkup:
    """Dynamic, paginated, and persona-driven main menu keyboard with Telegram Mini App support."""
    persona = get_user_persona(chat_id)

    # Common Top Web App Button
    webapp_btn = [
        InlineKeyboardButton("📱 បើក Control Center (Mini App)", web_app=WebAppInfo(url=WEBAPP_URL))
    ]

    holiday_sub = is_subscribed(chat_id)
    holiday_btn_text = "🔕 បិទបុណ្យជាតិ 4AM" if holiday_sub else "🔔 បើកបុណ្យជាតិ 4AM"
    holiday_callback = "btn_unsubscribe" if holiday_sub else "btn_subscribe"

    w_settings = get_user_weather_settings(chat_id)
    weather_active = w_settings.get("is_active", True)
    weather_btn_text = "🔕 បិទអាកាសធាតុ 5AM" if weather_active else "🌅 បើកអាកាសធាតុ 5AM"
    weather_callback = "btn_toggle_weather_off" if weather_active else "btn_toggle_weather_on"

    ai_active = is_ai_mode(chat_id)
    ai_btn_text = "💬 បិទ Continuous AI" if ai_active else "🤖 បើក Continuous AI"

    from database import is_auto_clean_enabled
    auto_clean_active = is_auto_clean_enabled(chat_id)
    auto_clean_text = "🧹 Auto-Clean: ✅" if auto_clean_active else "🧹 Auto-Clean: ❌"

    keyboard = [webapp_btn]

    # PERSONA 1: STUDENT
    if persona == "student":
        keyboard.extend([
            [
                InlineKeyboardButton("📚 ដោះស្រាយលំហាត់ AI", callback_data="btn_ai_vision_help"),
                InlineKeyboardButton("📄 Chat with PDF (/pdf)", callback_data="btn_pdf_help"),
            ],
            [
                InlineKeyboardButton("🌐 បកប្រែភាសា Pro", callback_data="btn_translate_help"),
                InlineKeyboardButton("✍️ ពិនិត្យអក្ខរាវិរុទ្ធ", callback_data="btn_check_help"),
            ],
            [
                InlineKeyboardButton("📝 សង្ខេប YouTube AI", callback_data="btn_summarize_help"),
                InlineKeyboardButton("🎧 Web Article ➔ Podcast", callback_data="btn_podcast_help"),
            ],
            [
                InlineKeyboardButton("💻 Code Runner (/code)", callback_data="btn_code_menu"),
                InlineKeyboardButton(ai_btn_text, callback_data="btn_toggle_aimode"),
            ],
            [
                InlineKeyboardButton("🎭 ប្តូរ Persona", callback_data="btn_choose_persona"),
                InlineKeyboardButton("🌐 មើល Menu ទាំងអស់ (Slider)", callback_data="set_persona_all"),
            ]
        ])

    # PERSONA 2: BUSINESS / MERCHANT
    elif persona == "business":
        keyboard.extend([
            [
                InlineKeyboardButton("🧾 ស្កេនវិក្កយបត្រ AI", callback_data="btn_scan_receipt_help"),
                InlineKeyboardButton("📊 ចំណូល-ចំណាយ (Budget)", callback_data="btn_budget"),
            ],
            [
                InlineKeyboardButton("📈 ក្រាហ្វិក Donut Chart", callback_data="btn_budget_chart"),
                InlineKeyboardButton("📥 ទាញយកជា Excel", callback_data="btn_budget_excel"),
            ],
            [
                InlineKeyboardButton("💧 ដាក់ Watermark ទំនិញ", callback_data="btn_photo_watermark_help"),
                InlineKeyboardButton("🌐 បង្កើត Web អាជីវកម្ម", callback_data="btn_web_builder"),
            ],
            [
                InlineKeyboardButton("💵 តម្លៃមាស & អត្រា NBC", callback_data="btn_finance"),
                InlineKeyboardButton("✂️ កាត់ Background រូប", callback_data="btn_photo_rembg_help"),
            ],
            [
                InlineKeyboardButton("🎬 AI Caption Studio", callback_data="btn_content_help"),
                InlineKeyboardButton("🚗 ធ្វើដំណើរ & ឡាន (/trip)", callback_data="btn_trip_menu"),
            ],
            [
                InlineKeyboardButton("🎭 ប្តូរ Persona", callback_data="btn_choose_persona"),
                InlineKeyboardButton("🌐 មើល Menu ទាំងអស់ (Slider)", callback_data="set_persona_all"),
            ]
        ])

    # PERSONA 3: CREATOR & MEDIA
    elif persona == "creator":
        keyboard.extend([
            [
                InlineKeyboardButton("📥 របៀបទាញយក 4K/8K", callback_data="btn_video_help"),
                InlineKeyboardButton("🎧 YouTube Playlist Batch", callback_data="btn_playlist_help"),
            ],
            [
                InlineKeyboardButton("🎨 បង្កើតរូបភាព AI (/imagine)", callback_data="btn_imagine_help"),
                InlineKeyboardButton("🌌 ធ្វើឱ្យរូបច្បាស់ 4K & 8K", callback_data="btn_photo_enhance_help"),
            ],
            [
                InlineKeyboardButton("✂️ កាត់តវីដេអូ (/trim)", callback_data="btn_trim_help"),
                InlineKeyboardButton("🎞️ បម្លែងវីដេអូជា GIF (/gif)", callback_data="btn_gif_help"),
            ],
            [
                InlineKeyboardButton("📑 ទាញយក Subtitle ខ្មែរ", callback_data="btn_subtitle_help"),
                InlineKeyboardButton("📻 ឃ្លាំងចម្រៀង @Song182", url="https://t.me/Song182"),
            ],
            [
                InlineKeyboardButton("🎭 ប្តូរ Persona", callback_data="btn_choose_persona"),
                InlineKeyboardButton("🌐 មើល Menu ទាំងអស់ (Slider)", callback_data="set_persona_all"),
            ]
        ])

    # PERSONA 4: ALL-IN-ONE PAGINATED SLIDER
    else:
        if page == 1:
            keyboard.extend([
                [
                    InlineKeyboardButton("🎨 បង្កើតរូបភាព AI (/imagine)", callback_data="btn_imagine_help"),
                    InlineKeyboardButton("📝 សង្ខេបវីដេអូ AI (/sum)", callback_data="btn_summarize_help"),
                ],
                [
                    InlineKeyboardButton("✂️ Viral Shorts (/shorts)", callback_data="btn_shorts_help"),
                    InlineKeyboardButton("📅 Calendar Sync (/event)", callback_data="btn_event_help"),
                ],
                [
                    InlineKeyboardButton("📥 របៀបទាញយកវីដេអូ", callback_data="btn_video_help"),
                    InlineKeyboardButton("🎧 ស្វែងរកចម្រៀង MP3", callback_data="btn_music_help"),
                ],
                [
                    InlineKeyboardButton("🌌 Super-Res 4K & 8K", callback_data="btn_photo_enhance_help"),
                    InlineKeyboardButton("🗣️ អានជាសំឡេង (/speak)", callback_data="btn_speak_help"),
                ],
                [
                    InlineKeyboardButton(ai_btn_text, callback_data="btn_toggle_aimode"),
                    InlineKeyboardButton("💡 ការណែនាំ (Help)", callback_data="btn_help"),
                ],
                [
                    InlineKeyboardButton("📄 [1/3] ពេញនិយម", callback_data="noop"),
                    InlineKeyboardButton("បន្ទាប់ ➡️", callback_data="menu_page_2"),
                ],
                [
                    InlineKeyboardButton("🎭 ជ្រើសរើស Persona (Role Mode)", callback_data="btn_choose_persona")
                ]
            ])
        elif page == 2:
            keyboard.extend([
                [
                    InlineKeyboardButton("📊 ចំណូល-ចំណាយ (Budget)", callback_data="btn_budget"),
                    InlineKeyboardButton("🧾 ស្កេនវិក្កយបត្រ", callback_data="btn_scan_receipt_help"),
                ],
                [
                    InlineKeyboardButton("💰 សេដ្ឋកិច្ច / មាស / សាំង", callback_data="btn_finance"),
                    InlineKeyboardButton("📈 ផ្សារ Crypto & TON", callback_data="btn_crypto_menu"),
                ],
                [
                    InlineKeyboardButton("📄 Chat with PDF (/pdf)", callback_data="btn_pdf_help"),
                    InlineKeyboardButton("🗜️ File Master (/compress)", callback_data="btn_compress_help"),
                ],
                [
                    InlineKeyboardButton("📝 រូបភាព ➔ Word (.docx)", callback_data="btn_word_help"),
                    InlineKeyboardButton("📊 រូបភាព ➔ Excel (.xlsx)", callback_data="btn_excel_help"),
                ],
                [
                    InlineKeyboardButton("🌐 បកប្រែ Pro (/translate)", callback_data="btn_translate_help"),
                    InlineKeyboardButton("✍️ ពិនិត្យអក្ខរាវិរុទ្ធ", callback_data="btn_check_help"),
                ],
                [
                    InlineKeyboardButton("⬅️ ថយក្រោយ", callback_data="menu_page_1"),
                    InlineKeyboardButton("📄 [2/3] ហិរញ្ញវត្ថុ", callback_data="noop"),
                    InlineKeyboardButton("បន្ទាប់ ➡️", callback_data="menu_page_3"),
                ],
                [
                    InlineKeyboardButton("🎭 ជ្រើសរើស Persona (Role Mode)", callback_data="btn_choose_persona")
                ]
            ])
        else: # Page 3
            keyboard.extend([
                [
                    InlineKeyboardButton(weather_btn_text, callback_data=weather_callback),
                    InlineKeyboardButton(holiday_btn_text, callback_data=holiday_callback),
                ],
                [
                    InlineKeyboardButton("⏰ សារដាស់តឿន (/remind)", callback_data="btn_reminders"),
                    InlineKeyboardButton("✂️ កាត់វីដេអូ & GIF (/trim)", callback_data="btn_trim_help"),
                ],
                [
                    InlineKeyboardButton("💧 ដាក់ Watermark", callback_data="btn_photo_watermark_help"),
                    InlineKeyboardButton("✂️ កាត់ Background (/rembg)", callback_data="btn_photo_rembg_help"),
                ],
                [
                    InlineKeyboardButton("🌐 បង្កើត Web (30s)", callback_data="btn_web_builder"),
                    InlineKeyboardButton("📧 អ៊ីមែល 10-Min (/mail)", callback_data="btn_tempmail"),
                ],
                [
                    InlineKeyboardButton("🔍 ស្កេន Link បោក (/scan)", callback_data="btn_scam_help"),
                    InlineKeyboardButton("💻 Code Runner (/code)", callback_data="btn_code_menu"),
                ],
                [
                    InlineKeyboardButton(auto_clean_text, callback_data="btn_toggle_autoclean"),
                    InlineKeyboardButton("🖥️ Local API 2GB", callback_data="btn_botserver_info"),
                ],
                [
                    InlineKeyboardButton("⬅️ ថយក្រោយ", callback_data="menu_page_2"),
                    InlineKeyboardButton("📄 [3/3] ឧបករណ៍", callback_data="noop"),
                ],
                [
                    InlineKeyboardButton("🎭 ជ្រើសរើស Persona (Role Mode)", callback_data="btn_choose_persona")
                ]
            ])

    return InlineKeyboardMarkup(keyboard)

def get_crypto_keyboard() -> InlineKeyboardMarkup:
    """Action keyboard for Crypto & TON Live Watcher."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("💎 TON (Telegram)", callback_data="btn_crypto_coin_TON"),
            InlineKeyboardButton("₿ Bitcoin (BTC)", callback_data="btn_crypto_coin_BTC"),
        ],
        [
            InlineKeyboardButton("🔷 Ethereum", callback_data="btn_crypto_coin_ETH"),
            InlineKeyboardButton("🟣 Solana", callback_data="btn_crypto_coin_SOL"),
        ],
        [
            InlineKeyboardButton("🔔 កំណត់ Alert", callback_data="btn_crypto_set_alert"),
            InlineKeyboardButton("📋 Alerts របស់ខ្ញុំ", callback_data="btn_crypto_my_alerts"),
        ],
        [
            InlineKeyboardButton("🔄 Refresh តម្លៃ", callback_data="btn_crypto_refresh"),
            InlineKeyboardButton("🔙 Menu ដើម", callback_data="btn_back_main"),
        ]
    ])

def get_content_keyboard(active_mode: str = "all") -> InlineKeyboardMarkup:
    """Action keyboard for AI Social Content & TikTok Script Studio."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🛍️ Facebook Post", callback_data="btn_content_view_fb"),
            InlineKeyboardButton("🎬 TikTok Script", callback_data="btn_content_view_tiktok"),
        ],
        [
            InlineKeyboardButton("📋 មើលទាំងអស់ (All)", callback_data="btn_content_view_all"),
            InlineKeyboardButton("🔄 បង្កើតថ្មី (Regenerate)", callback_data="btn_content_regen"),
        ],
        [
            InlineKeyboardButton("💡 របៀបប្រើ / គំរូ", callback_data="btn_content_help"),
            InlineKeyboardButton("🔙 Menu ដើម", callback_data="btn_back_main"),
        ]
    ])

def get_persistent_bottom_keyboard() -> ReplyKeyboardMarkup:
    """Persistent reply keyboard displayed at the bottom of the chat."""
    keyboard = [
        [KeyboardButton("📊 ចំណូល-ចំណាយ"), KeyboardButton("💰 សេដ្ឋកិច្ច/មាស/សាំង")],
        [KeyboardButton("📈 Crypto & TON"), KeyboardButton("🌤️ អាកាសធាតុ")],
        [KeyboardButton("📍 ផ្ញើទីតាំង GPS", request_location=True), KeyboardButton("⏰ Reminders")],
        [KeyboardButton("✨ AI Chat"), KeyboardButton("🧹 សម្អាតសារ"), KeyboardButton("🏠 ផ្ទាំង Menu មេ")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_back_keyboard() -> InlineKeyboardMarkup:
    """Standard back button returning to main menu."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 ត្រឡប់ទៅ Menu ដើម", callback_data="btn_back_main")]
    ])

def get_briefing_keyboard() -> InlineKeyboardMarkup:
    """Action keyboard for VIP Morning Executive Briefing."""
    keyboard = [
        [
            InlineKeyboardButton("🔄 Refresh ព័ត៌មាន", callback_data="btn_refresh_briefing"),
            InlineKeyboardButton("🌤️ អាកាសធាតុឥឡូវ", callback_data="btn_weather_now"),
        ],
        [
            InlineKeyboardButton("⏰ បន្ថែម Reminder", callback_data="btn_reminders"),
            InlineKeyboardButton("💰 សេដ្ឋកិច្ច/មាស/សាំង", callback_data="btn_finance"),
        ],
        [InlineKeyboardButton("🔙 ត្រឡប់ទៅ Menu ដើម", callback_data="btn_back_main")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_trip_menu_keyboard() -> InlineKeyboardMarkup:
    """Keyboard for CamRoad Trip Planner destinations."""
    keyboard = [
        [
            InlineKeyboardButton("🏛️ សៀមរាប (អង្គរ)", callback_data="btn_trip_dest_siemreap"),
            InlineKeyboardButton("🏖️ ព្រះសីហនុ (ល្បឿនលឿន)", callback_data="btn_trip_dest_sihanoukville"),
        ],
        [
            InlineKeyboardButton("⛰️ កំពត / កែប", callback_data="btn_trip_dest_kampot"),
            InlineKeyboardButton("🌾 បាត់ដំបង", callback_data="btn_trip_dest_battambang"),
        ],
        [
            InlineKeyboardButton("🌲 មណ្ឌលគិរី", callback_data="btn_trip_dest_mondulkiri"),
            InlineKeyboardButton("🏞️ កោះកុង", callback_data="btn_trip_dest_kohkong"),
        ],
        [
            InlineKeyboardButton("🔧 វិភាគកុងទ័រឡាន (/car)", callback_data="btn_car_diag_help"),
            InlineKeyboardButton("🔙 Menu ដើម", callback_data="btn_back_main"),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_code_menu_keyboard() -> InlineKeyboardMarkup:
    """Keyboard for Code Runner & Debugger."""
    keyboard = [
        [
            InlineKeyboardButton("▶️ Run Sample (Hello & Math)", callback_data="btn_code_sample_1"),
            InlineKeyboardButton("▶️ Run Sample (Data & Loops)", callback_data="btn_code_sample_2"),
        ],
        [
            InlineKeyboardButton("🐞 ជំនួយការកែកូដ (Debug)", callback_data="btn_code_debug_help"),
            InlineKeyboardButton("🔙 Menu ដើម", callback_data="btn_back_main"),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

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

    # 4. Update tracking & schedule for 20-min auto-delete
    context.user_data["last_bot_msg_id"] = sent.message_id
    context.user_data["last_menu_id"] = sent.message_id
    try:
        from database import record_auto_clean_message
        record_auto_clean_message(chat_id, sent.message_id)
    except Exception:
        pass
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
        text=get_welcome_text(first_name, chat_id=chat.id),
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
    Handle /clean or /clear [count|all] to wipe out ALL messages (both old and new)
    and reset chat to a 100% clean state with a single fresh menu.
    """
    chat = update.effective_chat
    user = update.effective_user
    current_msg = update.message
    current_msg_id = current_msg.message_id if current_msg else None
    chat_id = chat.id

    from services.chat_cleaner_service import purge_chat_history, format_clean_notice_text

    sweep_depth = None
    if context.args:
        raw_arg = str(context.args[0]).lower().strip()
        if raw_arg in ["all", "max", "full", "ទាំងអស់", "clearall"]:
            sweep_depth = max(1000, current_msg_id if current_msg_id else 1000)
        else:
            try:
                sweep_depth = min(max(int(raw_arg), 10), 2000)
            except ValueError:
                sweep_depth = None

    # Delete the /clean command message itself first if in private chat
    if current_msg and chat.type == "private":
        try:
            await current_msg.delete()
        except Exception:
            pass

    extra_ids = []
    if current_msg_id:
        extra_ids.append(current_msg_id)
    if context.user_data.get("last_menu_id"):
        extra_ids.append(context.user_data["last_menu_id"])
    if context.user_data.get("last_bot_msg_id"):
        extra_ids.append(context.user_data["last_bot_msg_id"])
    if context.user_data.get("last_remind_msg_id"):
        extra_ids.append(context.user_data["last_remind_msg_id"])

    # Purge all messages across chat history (both old and new)
    await purge_chat_history(
        bot=context.bot,
        chat_id=chat_id,
        current_msg_id=current_msg_id,
        sweep_depth=sweep_depth,
        extra_ids=extra_ids
    )

    # Clear stored tracking IDs in user_data
    context.user_data.pop("last_remind_msg_id", None)
    context.user_data.pop("last_menu_id", None)
    context.user_data.pop("last_bot_msg_id", None)

    clean_notice = format_clean_notice_text()
    sent_menu = await context.bot.send_message(
        chat_id=chat.id,
        text=clean_notice,
        reply_markup=get_main_menu_keyboard(chat.id),
        parse_mode="Markdown"
    )
    context.user_data["last_menu_id"] = sent_menu.message_id
    context.user_data["last_bot_msg_id"] = sent_menu.message_id
    try:
        from database import record_auto_clean_message
        record_auto_clean_message(chat_id, sent_menu.message_id)
    except Exception:
        pass

async def autoclean_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Toggle twice-daily auto-clean (12:00 PM & 12:00 AM Midnight): /autoclean."""
    chat_id = update.effective_chat.id
    from database import is_auto_clean_enabled, set_auto_clean_enabled
    current = is_auto_clean_enabled(chat_id)
    new_state = not current
    set_auto_clean_enabled(chat_id, new_state)
    
    if new_state:
        msg = (
            "🧹 *បានបើកមុខងារ Auto-Clean History (១២ ថ្ងៃ & ១២ យប់)!* ✅\n\n"
            "Bot នឹងសម្អាតប្រវត្តិសារទាំងអស់ដោយស្វ័យប្រវត្ត ២ ដងក្នុងមួយថ្ងៃ៖\n"
            "• ⏰ **ម៉ោង ១២:០០ ថ្ងៃត្រង់** (ម៉ោងនៅកម្ពុជា)\n"
            "• ⏰ **ម៉ោង ១២:០០ យប់ (អធ្រាត្រ)** (ម៉ោងនៅកម្ពុជា)\n\n"
            "ជួយឱ្យការជជែករបស់អ្នកមានសភាពស្អាតស្រឡះជានិច្ច និងគ្មានសារចាស់ៗកកកុញឡើយ។"
        )
    else:
        msg = (
            "🔕 *បានបិទមុខងារ Auto-Clean History!* ❌\n\n"
            "សារនឹងមិនត្រូវសម្អាតស្វ័យប្រវត្តនៅម៉ោង ១២:០០ ថ្ងៃត្រង់ និង ១២:០០ យប់ទៀតឡើយ។"
        )
    await send_clean_response(update, context, msg, reply_markup=get_back_keyboard())

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

async def memory_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """View stored Long-Term Memories & User Profile: /memory."""
    chat_id = update.effective_chat.id
    from services.memory_service import format_user_memory_display
    msg = format_user_memory_display(chat_id)
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🗑️ លុបការចងចាំទាំងអស់ (/forget)", callback_data="btn_clear_longterm_memory")],
        [InlineKeyboardButton("🔙 Menu ដើម", callback_data="btn_back_main")]
    ])
    await send_clean_response(update, context, msg, reply_markup=kb)

async def forget_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Clear all stored Long-Term Memories: /forget."""
    chat_id = update.effective_chat.id
    from database import clear_user_memories
    from services.cache_service import cache_delete
    count = clear_user_memories(chat_id)
    cache_delete(f"mem_prompt_{chat_id}")
    msg = (
        f"🧹 *បានសម្អាត Long-Term Memory រួចរាល់ហើយ!* ✨\n\n"
        f"បានលុបព័ត៌មានចងចាំចំនួន {count} ចំណុច។\n"
        f"Bot បានត្រលប់ទៅសភាពដើមវិញដោយគ្មានការចងចាំទម្លាប់ចាស់ៗឡើយ។"
    )
    await send_clean_response(update, context, msg, reply_markup=get_back_keyboard())

async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Live Google Search Grounding with Gemini: /search <query>."""
    chat_id = update.effective_chat.id
    query = " ".join(context.args) if context.args else ""
    if not query:
        msg = (
            "🌐 *ស្វែងរកព័ត៌មាន Real-Time ជាមួយ Google Search Grounding* 🔎\n\n"
            "លោកអ្នកអាចសួរព័ត៌មានទាន់ហេតុការណ៍ តម្លៃហាងឆេង ឬលទ្ធផលបន្តផ្ទាល់បាន!\n\n"
            "👉 *របៀបប្រើប្រាស់៖*\n"
            "• `/search តម្លៃមាស និងប្រេងឥន្ធនៈថ្ងៃនេះនៅកម្ពុជា`\n"
            "• `/search លទ្ធផលបាល់ទាត់យប់មិញ`\n"
            "• `/search ព័ត៌មានថ្មីៗបំផុតថ្ងៃនេះ`"
        )
        await send_clean_response(update, context, msg, reply_markup=get_back_keyboard())
        return

    status = await update.message.reply_text("🌐 *កំពុងស្វែងរកទិន្នន័យផ្ទាល់ពី Google Search...* ⏳", parse_mode="Markdown")
    try:
        from services.ai_service import query_gemini_live_search
        ans = await query_gemini_live_search(query, chat_id=chat_id)
        from handlers.command_handlers import safe_edit_text
        await safe_edit_text(status, ans, reply_markup=get_back_keyboard())
    except Exception as e:
        await status.edit_text(f"❌ កំហុសក្នុងការស្វែងរក៖ {e}")

async def briefing_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generate VIP Morning Executive Briefing: /briefing."""
    chat_id = update.effective_chat.id
    user = update.effective_user
    first_name = user.first_name if user else "លោកអ្នក"
    status = await update.message.reply_text("👑 *កំពុងរៀបចំរបាយការណ៍សង្ខេប VIP ជូនអ្នក...* ⏳", parse_mode="Markdown")
    try:
        from services.briefing_service import generate_executive_briefing
        briefing_text = await generate_executive_briefing(chat_id, user_name=first_name)
        await safe_edit_text(status, briefing_text, reply_markup=get_briefing_keyboard())
    except Exception as e:
        logger.error(f"Error in briefing_command: {e}")
        await status.edit_text(f"❌ មិនអាចទាញយករបាយការណ៍បានទេ៖ {e}")

async def compress_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Help and options for compressing PDF and images: /compress."""
    msg = (
        "🗜️ *មជ្ឈមណ្ឌលបង្រួម & បម្លែងឯកសារ (Universal File Master)* ✨\n\n"
        "លោកអ្នកអាចបង្រួមទំហំឯកសារដើម្បីផ្ញើបានលឿន និងសន្សំសំចៃ Internet៖\n\n"
        "📄 *១. បង្រួមឯកសារ PDF (Compress PDF)៖*\n"
        "• គ្រាន់តែផ្ញើ File PDF ចូលមកក្នុង Bot\n"
        "• រួចចុចប៊ូតុង `🗜️ បង្រួមទំហំ (Compress)` ខាងក្រោម File នោះ!\n\n"
        "🔄 *២. បម្លែង PDF ➔ Word (.docx)៖*\n"
        "• ផ្ញើ File PDF ➔ ចុចប៊ូតុង `🔄 បម្លែងទៅ Word (.docx)` ភ្លាមៗ!\n"
        "• លោកអ្នកនឹងទទួលបាន file Word សម្រាប់កែសម្រួលបានដោយសេរី។\n\n"
        "🖼️ *៣. បង្រួមរូបភាព (Compress Image)៖*\n"
        "• ផ្ញើរូបភាពចូលដោយផ្ទាល់ដើម្បីបង្រួមទំហំ KB/MB ដោយរក្សាភាពច្បាស់!"
    )
    await send_clean_response(update, context, msg, reply_markup=get_back_keyboard())

async def trip_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Plan trips in Cambodia, calculate road distance, duration, fuel cost & rest stops: /trip [destination]."""
    text = update.message.text or ""
    parts = text.split(maxsplit=1)
    arg = parts[1].strip() if len(parts) > 1 else ""

    if not arg:
        msg = (
            "🚗 *CamRoad Trip Planner (ជំនួយការធ្វើដំណើរកម្សាន្តកម្ពុជា)* 🛣️\n\n"
            "សូមជ្រើសរើសគោលដៅទេសចរណ៍ពេញនិយមខាងក្រោម ដើម្បីគណនាចម្ងាយផ្លូវ "
            "រយៈពេល ថ្លៃសាំងប៉ាន់ស្មាន និងកន្លែងឈប់សម្រាកល្បីៗ៖\n\n"
            "💡 _ឬអ្នកអាចវាយឈ្មោះខេត្តផ្ទាល់៖_ `/trip <គោលដៅ>`\n"
            "ឧទាហរណ៍៖ `/trip សៀមរាប` ឬ `/trip កំពត` ឬ `/trip ភ្នំពេញ ទៅ សៀមរាប`"
        )
        await send_clean_response(update, context, msg, reply_markup=get_trip_menu_keyboard())
        return

    origin = "រាជធានីភ្នំពេញ"
    destination_str = arg
    if "ទៅ" in arg:
        subparts = arg.split("ទៅ", 1)
        origin = subparts[0].replace("ពី", "").strip() or "រាជធានីភ្នំពេញ"
        destination_str = subparts[1].strip()
    elif "to" in arg.lower():
        subparts = re.split(r"\bto\b", arg, flags=re.IGNORECASE)
        origin = subparts[0].replace("from", "").strip() or "រាជធានីភ្នំពេញ"
        destination_str = subparts[1].strip()

    dest_data = match_destination(destination_str)
    if dest_data:
        trip = calculate_trip_details(dest_data, origin=origin)
        report = format_trip_report(trip)
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🗺️ បើកផែនទីនាំផ្លូវ (Google Maps)", url=trip["maps_dir_url"])],
            [
                InlineKeyboardButton("🚗 ជ្រើសរើសគោលដៅផ្សេង", callback_data="btn_trip_menu"),
                InlineKeyboardButton("🔙 Menu ដើម", callback_data="btn_back_main")
            ]
        ])
        await send_clean_response(update, context, report, reply_markup=kb)
    else:
        dest_clean = destination_str.strip()
        maps_url = f"https://www.google.com/maps/dir/?api=1&origin={urllib.parse.quote(origin)}&destination={urllib.parse.quote(dest_clean)}"
        msg = (
            f"🚗 *ផែនការធ្វើដំណើរទៅកាន់៖* *{dest_clean}*\n\n"
            f"🚩 *ចេញដំណើរពី:* {origin}\n"
            f"🏁 *គោលដៅ:* {dest_clean}\n\n"
            f"🗺️ [ចុចទីនេះដើម្បីបើកមើលផ្លូវ និងចម្ងាយលើ Google Maps]({maps_url})\n\n"
            f"💡 _សម្រាប់ខេត្តទេសចរណ៍សំខាន់ៗ (សៀមរាប, ព្រះសីហនុ, កំពត, បាត់ដំបង, មណ្ឌលគិរី, កោះកុង...) "
            f"Bot អាចគណនាថ្លៃសាំង និងប្រាប់កន្លែងឈប់សម្រាកលម្អិតបានភ្លាមៗ!_"
        )
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🗺️ បើកមើលលើ Google Maps", url=maps_url)],
            [
                InlineKeyboardButton("🚗 បញ្ជីគោលដៅពេញនិយម", callback_data="btn_trip_menu"),
                InlineKeyboardButton("🔙 Menu ដើម", callback_data="btn_back_main")
            ]
        ])
        await send_clean_response(update, context, msg, reply_markup=kb)

async def car_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Car Diagnostic help & dashboard scanner info: /car."""
    msg = (
        "🔧 *Car Dashboard Diagnostic (ជំនួយការពិនិត្យកុងទ័រឡាន AI)* 🚗\n\n"
        "រាល់ពេលដែលរថយន្តរបស់អ្នកលោតភ្លើង Warning Error នៅលើកុងទ័រ៖\n\n"
        "📸 *របៀបប្រើប្រាស់ងាយៗ៖*\n"
        "1. ថតរូបកុងទ័រឡានដែលមានលោតភ្លើងសញ្ញានោះ\n"
        "2. ផ្ញើរូបភាពចូលមកក្នុង Bot នេះភ្លាមៗ (អាចដាក់ Caption `/car` ឬផ្ញើរូបធម្មតា)\n"
        "3. AI នឹងជួយពិនិត្យ៖\n"
        "   • ឈ្មោះសញ្ញា & កម្រិតគ្រោះថ្នាក់ (🔴 ធ្ងន់ធ្ងរ / 🟡 មធ្យម)\n"
        "   • មូលហេតុដែលអាចកើតមានឡើង\n"
        "   • ដំណោះស្រាយបន្ទាន់សម្រាប់អ្នកបើកបរ!\n\n"
        "💡 _ជួយអ្នកសន្សំសំចៃពេលវេលា និងដឹងបញ្ហាមុនពេលទៅជួបជាង!_"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🚗 គណនាការធ្វើដំណើរ (/trip)", callback_data="btn_trip_menu")],
        [InlineKeyboardButton("🔙 Menu ដើម", callback_data="btn_back_main")]
    ])
    await send_clean_response(update, context, msg, reply_markup=kb)

async def code_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Code Runner & Debugger Hub: /code."""
    msg = (
        "💻 *មជ្ឈមណ្ឌល Code Runner & AI Debugger ក្នុង Telegram* ⚡\n\n"
        "👉 *១. Run កូដ Python ផ្ទាល់ក្នុង Telegram៖*\n"
        "• វាយ `/run <កូដ Python>`\n"
        "• ឧទាហរណ៍៖\n"
        "```python\n/run\nfor i in range(1, 6):\n    print('★' * i)\n```\n\n"
        "👉 *២. ជួសជុលកូដ Error (AI Debugger)៖*\n"
        "• វាយ `/debug <កូដដែលមាន Bug>`\n"
        "• គាំទ្រ: Python, JS, PHP, HTML, CSS, SQL, C++, Java, Dart\n\n"
        "💡 _អ្នកអាចចុច Run កូដគំរូខាងក្រោមដើម្បីតេស្តភ្លាមៗ៖_"
    )
    await send_clean_response(update, context, msg, reply_markup=get_code_menu_keyboard())

async def run_code_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Run sandboxed Python code: /run <code>."""
    text = update.message.text or ""
    parts = text.split(maxsplit=1)
    code = parts[1].strip() if len(parts) > 1 else ""

    if not code:
        sample_tip = (
            "💻 *របៀបប្រើប្រាស់ Python Code Runner ⚡*\n\n"
            "សូមវាយ `/run` អមជាមួយកូដ Python របស់អ្នក៖\n\n"
            "ឧទាហរណ៍៖\n"
            "```python\n/run\nx = [10, 20, 30]\nprint('ផលបូក:', sum(x))\n```\n\n"
            "💡 _ឬចុចប៊ូតុងខាងក្រោមដើម្បី Run កូដគំរូ៖_"
        )
        await send_clean_response(update, context, sample_tip, reply_markup=get_code_menu_keyboard())
        return

    # Clean markdown backticks if user wrapped in ```python ... ```
    if code.startswith("```"):
        lines = code.split("\n")
        if len(lines) >= 2 and lines[-1].strip().startswith("```"):
            code = "\n".join(lines[1:-1]).strip()

    status = await update.message.reply_text("⚡ *កំពុងដំណើរការកូដក្នុង Python Sandbox...* ⏳", parse_mode="Markdown")
    res = execute_python_code_sandboxed(code)
    report = format_execution_result(res, code)
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("💻 Code Runner Hub", callback_data="btn_code_menu")],
        [InlineKeyboardButton("🔙 Menu ដើម", callback_data="btn_back_main")]
    ])
    await safe_edit_text(status, report, reply_markup=kb)

async def debug_code_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Debug and fix programming code using AI: /debug <code>."""
    text = update.message.text or ""
    parts = text.split(maxsplit=1)
    code = parts[1].strip() if len(parts) > 1 else ""

    if not code:
        tip = (
            "🐞 *របៀបប្រើប្រាស់ AI Code Debugger ✨*\n\n"
            "សូមវាយ `/debug` អមជាមួយកូដដែលមានបញ្ហា Error៖\n\n"
            "ឧទាហរណ៍៖\n"
            "```python\n/debug\ndef add(a, b)\n    return a + b\nprint(add(5))\n```\n\n"
            "AI នឹងពន្យល់មូលហេតុ និងផ្ដល់កូដដែលបានកែសម្រួលត្រឹមត្រូវភ្លាមៗ!"
        )
        await send_clean_response(update, context, tip, reply_markup=get_back_keyboard())
        return

    status = await update.message.reply_text("🐞 *AI កំពុងពិនិត្យ និងជួសជុលកូដរបស់អ្នក...* ⏳", parse_mode="Markdown")
    debug_report = await debug_and_explain_code(code)
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("💻 Code Runner Hub", callback_data="btn_code_menu")],
        [InlineKeyboardButton("🔙 Menu ដើម", callback_data="btn_back_main")]
    ])
    await safe_edit_text(status, debug_report, reply_markup=kb)

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
            InlineKeyboardButton("📊 ក្រាហ្វិក (Pie Chart)", callback_data="btn_budget_chart"),
            InlineKeyboardButton("📥 ទាញយក Excel (.xlsx)", callback_data="btn_budget_excel"),
        ],
        [
            InlineKeyboardButton("🧾 របៀបស្កេនវិក្កយបត្រ", callback_data="btn_scan_receipt_help"),
            InlineKeyboardButton("🔄 ធ្វើបច្ចុប្បន្នភាព", callback_data="btn_budget"),
        ],
        [
            InlineKeyboardButton("🗑️ សម្អាតប្រវត្តិ", callback_data="btn_clear_expenses_ask"),
            InlineKeyboardButton("🔙 Menu ដើម", callback_data="btn_back_main")
        ]
    ])
    await send_clean_response(update, context, report, reply_markup=keyboard)

async def chart_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generate budget pie chart image: /chart."""
    chat_id = update.effective_chat.id
    chart_bytes = generate_budget_pie_chart(chat_id)
    if chart_bytes:
        import io
        await update.message.reply_photo(
            photo=io.BytesIO(chart_bytes),
            caption="📊 *ក្រាហ្វិកវិភាគចំណាយតាមប្រភេទ (Donut / Pie Chart - 30 ថ្ងៃ)* ✨",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text("⚠️ មិនទាន់មានទិន្នន័យចំណាយសម្រាប់គូសក្រាហ្វិកនៅឡើយទេ។ សូមកត់ត្រាចំណាយជាមុនសិនណា៎! (ឧ. `/spend 5$ coffee`)")

async def excel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generate budget history Excel spreadsheet: /excel."""
    chat_id = update.effective_chat.id
    excel_bytes = generate_budget_excel(chat_id)
    import io
    today_str = datetime.now().strftime("%Y-%m-%d")
    await update.message.reply_document(
        document=io.BytesIO(excel_bytes),
        filename=f"budget_history_{today_str}.xlsx",
        caption=f"📈 *ឯកសារប្រវត្តិចំណូល-ចំណាយ Excel (.xlsx)*\n📅 កាលបរិច្ឆេទ៖ `{today_str}`",
        parse_mode="Markdown"
    )

async def listen_podcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Summarize web article and generate Khmer audio podcast: /listen <url> or /podcast <url>."""
    text = update.message.text or ""
    parts = text.split(maxsplit=1)
    url = parts[1].strip() if len(parts) > 1 else ""

    if not url or not (url.startswith("http://") or url.startswith("https://")):
        tip = (
            "🎧 *របៀបប្រើប្រាស់ Web Article to Audio Podcast៖*\n\n"
            "សូមវាយ `/listen <Link វេបសាយព័ត៌មាន ឬអត្ថបទ>`\n\n"
            "• ឧទាហរណ៍៖ `/listen https://freshnewsasia.com/...`\n\n"
            "Bot នឹងសង្ខេប ៣ ចំណុចធំៗ និងបង្កើតជា File សំឡេង (Khmer Audio Podcast) ឱ្យលោកអ្នកស្តាប់ភ្លាមៗ! 🎙️"
        )
        await send_clean_response(update, context, tip, reply_markup=get_back_keyboard())
        return

    status = await update.message.reply_text("🎧 *កំពុងអានគេហទំព័រ និងផលិតសំឡេង Podcast (Khmer Audio)...* ⏳", parse_mode="Markdown")
    podcast = await generate_article_podcast(url)

    if not podcast.get("success"):
        await safe_edit_text(status, podcast.get("bullet_summary", "❌ មិនអាចទាញយកព័ត៌មានពី Link នេះបានទេ។"))
        return

    await safe_edit_text(status, podcast["bullet_summary"], reply_markup=get_back_keyboard())

    if podcast.get("audio_bytes"):
        import io
        clean_title = podcast.get("title", "News Podcast")[:40]
        await update.message.reply_audio(
            audio=io.BytesIO(podcast["audio_bytes"]),
            title=clean_title,
            performer="Telegram Assistant Podcast",
            caption=f"🎙️ *ស្តាប់សេចក្តីសង្ខេបព័ត៌មាន Podcast ជាភាសាខ្មែរ* 🎧\n_ប្រភព៖ {url[:50]}_",
            parse_mode="Markdown"
        )

async def chord_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Find guitar/piano chords, strumming pattern, and lyrics: /chord <song_name>."""
    text = update.message.text or ""
    parts = text.split(maxsplit=1)
    song_name = parts[1].strip() if len(parts) > 1 else ""

    if not song_name:
        tip = (
            "🎸 *របៀបស្វែងរកបន្ទះ Chord ហ្គីតា/ព្យាណូ & ទំនុកច្រៀង៖*\n\n"
            "សូមវាយ៖ `/chord <ឈ្មោះបទចម្រៀង>`\n\n"
            "• ឧទាហរណ៍៖ `/chord ចិត្តអើយ` ឬ `/chord នឹកអូន` ឬ `/chord perfect`\n\n"
            "Bot នឹងបង្ហាញ Key, ចង្វាក់កេះហ្គីតា (Strumming), និងទំនុកច្រៀងអមជាមួយ Chord ភ្លាមៗ! 🎶"
        )
        await send_clean_response(update, context, tip, reply_markup=get_back_keyboard())
        return

    status = await update.message.reply_text(f"🎸 *កំពុងស្វែងរកបន្ទះ Chord & ទំនុកច្រៀងបទ '{song_name}'...* 🎶", parse_mode="Markdown")
    chord_sheet = await find_song_chords(song_name)
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🎧 ស្វែងរកចម្រៀង MP3", callback_data="btn_music_help")],
        [InlineKeyboardButton("🔙 Menu ដើម", callback_data="btn_back_main")]
    ])
    await safe_edit_text(status, chord_sheet, reply_markup=kb)

async def user_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Resolve Telegram username, search similar profiles, and display profile photo & phone number: /user <query>."""
    text = update.message.text or ""
    parts = text.split(maxsplit=1)
    query = parts[1].strip() if len(parts) > 1 else ""

    if not query:
        _, _, tip = validate_username_format("")
        await send_clean_response(update, context, tip, reply_markup=get_back_keyboard())
        return

    status = await update.message.reply_text("🔍 *កំពុងស្វែងរកគណនី Telegram រូប Profile & លេខទូរស័ព្ទ...* ⏳", parse_mode="Markdown")
    profile_data = await resolve_telegram_user(context.bot, query)
    card_text, keyboard = format_user_resolver_card(profile_data)

    photo_bytes = profile_data.get("photo_bytes")
    photo_url = profile_data.get("photo_url")
    photo_source = None
    if photo_bytes:
        import io
        photo_source = io.BytesIO(photo_bytes)
        photo_source.name = "profile.jpg"
    elif photo_url:
        photo_source = photo_url

    if photo_source and len(card_text) <= 1024:
        try:
            await update.message.reply_photo(
                photo=photo_source,
                caption=card_text,
                reply_markup=keyboard,
                parse_mode="Markdown"
            )
            try:
                await status.delete()
            except Exception:
                pass
            return
        except Exception as e_photo:
            logger.warning(f"Failed to send profile photo, falling back to text: {e_photo}")

    await safe_edit_text(status, card_text, reply_markup=keyboard)

async def crypto_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /crypto, /ton, /btc, /coin to display live market prices & alerts."""
    from services.crypto_service import fetch_crypto_prices, format_crypto_overview_card
    from services.finance_service import fetch_exchange_rates, fetch_gold_price

    rates = await fetch_exchange_rates() or {}
    usd_khr = rates.get("KHR", 4085.0)
    gold = await fetch_gold_price()

    crypto_data = await fetch_crypto_prices()
    card_text = format_crypto_overview_card(crypto_data, usd_khr_rate=usd_khr, gold_info=gold)

    await send_clean_response(
        update=update,
        context=context,
        text=card_text,
        reply_markup=get_crypto_keyboard(),
        parse_mode="Markdown"
    )

async def alert_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /alert <coin> <price> to set price drop/pump notifications."""
    from services.crypto_service import fetch_crypto_prices, parse_alert_input
    from database import add_crypto_alert, get_user_crypto_alerts

    chat_id = update.effective_chat.id
    raw_args = " ".join(context.args) if context.args else ""

    if not raw_args:
        user_alerts = get_user_crypto_alerts(chat_id)
        lines = [
            "🔔 *[របៀបកំណត់ Alert តម្លៃ Crypto & TON]* 📈\n",
            "លោកអ្នកអាចឱ្យ Bot ជួយតាមដានតម្លៃកាក់ និងផ្ញើសារប្រាប់ភ្លាមៗនៅពេលតម្លៃឡើងដល់ ឬធ្លាក់ចុះដល់គោលដៅ!\n",
            "• វាយ៖ `/alert <ឈ្មោះកាក់> <តម្លៃ>`\n",
            "• ឧទាហរណ៍៖ `/alert btc 85000` (ជូនដំណឹងពេល Bitcoin ឡើង/ធ្លាក់ដល់ $85,000)",
            "• ឧទាហរណ៍៖ `/alert ton 5.5` (ជូនដំណឹងពេល TON ឡើងដល់ $5.5)",
            "• ឧទាហរណ៍៖ `/alert eth 3200` (ជូនដំណឹងពេល Ethereum ឡើងដល់ $3,200)\n",
            "━━━━━━━━━━━━━━━━━━━━━━"
        ]
        if user_alerts:
            lines.append(f"📋 *Alerts សកម្មរបស់អ្នក ({len(user_alerts)})៖*")
            for a in user_alerts[:6]:
                cond_sym = "📈 ឡើងដល់" if a["condition"] == "above" else "📉 ធ្លាក់ដល់"
                lines.append(f"• *{a['symbol']}*: {cond_sym} `${a['target_price']:,.2f}` (កាលកំណត់: `${a['created_price']:,.2f}`)")
        else:
            lines.append("ℹ️ _បច្ចុប្បន្នអ្នកមិនទាន់មាន Alert សកម្មណាមួយឡើយ។_")

        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("📋 Alerts របស់ខ្ញុំ", callback_data="btn_crypto_my_alerts"), InlineKeyboardButton("📈 ផ្សារ Crypto", callback_data="btn_crypto_menu")],
            [InlineKeyboardButton("🔙 Menu ដើម", callback_data="btn_back_main")]
        ])
        await send_clean_response(update, context, "\n".join(lines), reply_markup=kb)
        return

    prices = await fetch_crypto_prices()
    success, sym, target, condition, curr_p, msg = parse_alert_input(raw_args, prices)
    if not success:
        await send_clean_response(update, context, msg, reply_markup=get_back_keyboard())
        return

    add_crypto_alert(chat_id, sym, target, condition, curr_p)
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 Alerts របស់ខ្ញុំ", callback_data="btn_crypto_my_alerts"), InlineKeyboardButton("📈 ផ្សារ Crypto", callback_data="btn_crypto_menu")],
        [InlineKeyboardButton("🔙 Menu ដើម", callback_data="btn_back_main")]
    ])
    await send_clean_response(update, context, msg, reply_markup=kb)

async def alerts_list_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /alerts or /myalerts to view and delete active price alerts."""
    from database import get_user_crypto_alerts
    chat_id = update.effective_chat.id
    alerts = get_user_crypto_alerts(chat_id)

    if not alerts:
        msg = (
            "📋 *បញ្ជី Price Alerts របស់អ្នក* 🔔\n\n"
            "ℹ️ _លោកអ្នកមិនទាន់មាន Alert សកម្មណាមួយឡើយ។_\n\n"
            "💡 *ដើម្បីបង្កើត Alert ថ្មី សូមវាយ៖*\n"
            "`/alert <កាក់> <តម្លៃ>` (ឧទាហរណ៍: `/alert btc 85000` ឬ `/alert ton 5.5`)"
        )
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ កំណត់ Alert ថ្មី", callback_data="btn_crypto_set_alert")],
            [InlineKeyboardButton("📈 ផ្សារ Crypto & TON", callback_data="btn_crypto_menu")],
            [InlineKeyboardButton("🔙 Menu ដើម", callback_data="btn_back_main")]
        ])
        await send_clean_response(update, context, msg, reply_markup=kb)
        return

    lines = [
        f"📋 *បញ្ជី Price Alerts សកម្មរបស់អ្នក ({len(alerts)})* 🔔\n",
        "ចុចប៊ូតុង **[🗑️ លុប]** ខាងក្រោម ដើម្បីលុប Alert ណាមួយដែលលែងត្រូវការ៖\n",
        "━━━━━━━━━━━━━━━━━━━━━━"
    ]
    buttons = []
    for a in alerts[:10]:
        aid = a["id"]
        sym = a["symbol"]
        cond = "📈 ឡើងដល់" if a["condition"] == "above" else "📉 ធ្លាក់ដល់"
        target = a["target_price"]
        lines.append(f"• *{sym}*: {cond} `${target:,.2f}`")
        buttons.append([
            InlineKeyboardButton(f"🗑️ លុប: {sym} ${target:,.2f}", callback_data=f"btn_crypto_del_alert_{aid}")
        ])

    buttons.append([
        InlineKeyboardButton("➕ បង្កើត Alert ថ្មី", callback_data="btn_crypto_set_alert"),
        InlineKeyboardButton("📈 ផ្សារ Crypto", callback_data="btn_crypto_menu")
    ])
    buttons.append([InlineKeyboardButton("🔙 Menu ដើម", callback_data="btn_back_main")])

    await send_clean_response(update, context, "\n".join(lines), reply_markup=InlineKeyboardMarkup(buttons))

async def content_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle /content, /caption, /post, /script to generate high-converting
    Facebook sales posts, 15s TikTok scripts, and trending hashtags from text or photos.
    """
    message = update.message
    chat_id = update.effective_chat.id
    raw_args = " ".join(context.args) if context.args else ""

    # Check if command is attached to or replies to a photo
    image_bytes = None
    target_photo = None
    if message and message.photo:
        target_photo = message.photo[-1]
    elif message and message.reply_to_message and message.reply_to_message.photo:
        target_photo = message.reply_to_message.photo[-1]
        if not raw_args and message.reply_to_message.caption:
            raw_args = message.reply_to_message.caption

    if target_photo:
        try:
            tg_file = await context.bot.get_file(target_photo.file_id)
            image_bytes = bytes(await tg_file.download_as_bytearray())
        except Exception as e:
            logger.debug(f"Could not download photo for content creator: {e}")

    if not raw_args and not image_bytes:
        tip = (
            "🎬 *[AI Content Creator Studio]* ✨\n\n"
            "ជំនួយការឆ្លាតវៃសម្រាប់ **អ្នកលក់អនឡាញ & TikToker** ជួយសរសេរ Caption ផុសលក់ដាច់, Script វីដេអូខ្លី ១៥ វិនាទី, និង Hashtags ល្បីៗស្វ័យប្រវត្តិ!\n\n"
            "💡 *របៀបប្រើប្រាស់ងាយៗ៖*\n"
            "• វាយ៖ `/caption <ឈ្មោះទំនិញ ឬប្រធានបទ>`\n"
            "   (ឧ. `/caption កាហ្វេដូងក្រអូប រសជាតិថ្មី`)\n"
            "   (ឧ. `/caption ឡេលាបស្បែក ស ភ្លឺថ្លាក្នុង ៧ ថ្ងៃ`)\n"
            "   (ឧ. `/caption អាវយឺតដៃខ្លី Oversize សាច់ត្រជាក់`)\n\n"
            "📸 *ឬគ្រាន់តែផ្ញើរូបថតផលិតផល* ដោយសរសេរភ្ជាប់ `/caption` ➔ AI នឹងស្កេនមើលផលិតផលក្នុងរូបភាព រួចរៀបចំ Caption និង Script វីដេអូជូនភ្លាមៗ! 🚀"
        )
        await send_clean_response(update, context, tip, reply_markup=get_back_keyboard())
        return

    topic = raw_args or "ផលិតផលក្នុងរូបភាព"
    status = await message.reply_text("✨ *AI កំពុងវិភាគ និងរៀបចំ Caption លក់ & Script TikTok...* ⏳", parse_mode="Markdown")

    from services.content_creator_service import generate_social_content, format_content_card
    content_data = await generate_social_content(topic=topic, image_bytes=image_bytes)

    # Cache content data in user_data for quick view switching (FB / TikTok / All)
    context.user_data["last_content_data"] = content_data

    card_text = format_content_card(content_data, view_mode="all")
    await safe_edit_text(status, card_text, reply_markup=get_content_keyboard("all"))

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
    """Search & download song MP3: /song <query> or reply to a photo with /song."""
    query = " ".join(context.args) if context.args else ""
    reply_msg = update.message.reply_to_message if update.message else None

    if reply_msg and reply_msg.photo:
        photo = reply_msg.photo[-1]
        status_msg = await update.message.reply_text("🖼️ *បានទទួលរូបភាព! AI កំពុងស្កេនរកឈ្មោះបទចម្រៀងពីរូបភាព...* 🔍🎶", parse_mode="Markdown")
        try:
            tg_file = await context.bot.get_file(photo.file_id)
            img_bytes = bytes(await tg_file.download_as_bytearray())
            from services.music_service import extract_song_query_from_image
            extracted_query = await extract_song_query_from_image(img_bytes, extra_hint=query)
            if not extracted_query:
                await safe_edit_text(status_msg, "❌ មិនអាចស្គាល់ឈ្មោះបទចម្រៀងពីរូបភាពនេះបានទេ។ សូមសាកល្បងវាយ `/song <ឈ្មោះបទ>` ដោយផ្ទាល់។")
                return
            query = extracted_query
            await safe_edit_text(status_msg, f"🔍 *បានស្កេនឃើញបទ៖* `{query}` 🎶\n_កំពុងទាញយក file MP3 កម្រិតច្បាស់..._")
        except Exception as e_scan:
            logger.warning(f"Error scanning song from reply photo: {e_scan}")
            await safe_edit_text(status_msg, f"❌ បរាជ័យក្នុងការស្កេនរូបភាព៖ {e_scan}")
            return
    elif not query:
        await update.message.reply_text(
            "🎧 *របៀបស្វែងរក និងទាញយកចម្រៀង MP3 320kbps៖*\n\n"
            "សូមវាយ៖ `/song <ឈ្មោះបទចម្រៀង ឬឈ្មោះតារា>`\n"
            "• ឧទាហរណ៍៖ `/song ស្រលាញ់គ្នាម្តងទៀតបានទេ`\n"
            "• ឧទាហរណ៍៖ `/song shape of you`\n\n"
            "📸 *ឬ Upload រូបភាព Screenshot បទចម្រៀងអមដោយ Caption:* `/song`\n"
            "Bot នឹងស្កេនរកឈ្មោះបទពីរូបភាព និងទាញយកជូនភ្លាមៗ!",
            parse_mode="Markdown"
        )
        return
    else:
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

        caption_html = (
            f"🎧 <b>{html.escape(res['title'])}</b>\n"
            f"👤 <b>តារាចម្រៀង:</b> {html.escape(res['performer'])}\n"
            f"⏱️ <b>រយៈពេល:</b> {res['duration_str']}\n\n"
            f"✨ Smart Assistant Bot 🎵"
        )

        sent_msg = None
        with open(file_path, "rb") as audio_file:
            try:
                sent_msg = await update.message.reply_audio(
                    audio=audio_file,
                    title=res["title"],
                    performer=res["performer"],
                    duration=dur,
                    caption=caption_html,
                    parse_mode="HTML",
                    read_timeout=300.0,
                    write_timeout=300.0,
                    connect_timeout=60.0,
                )
            except Exception as e_snd:
                logger.warning(f"HTML reply_audio failed, retrying plain text: {e_snd}")
                audio_file.seek(0)
                sent_msg = await update.message.reply_audio(
                    audio=audio_file,
                    title=res["title"],
                    performer=res["performer"],
                    duration=dur,
                    caption=f"🎧 {res['title']}\n👤 {res['performer']}\n⏱️ {res['duration_str']}\n\n✨ Smart Assistant Bot 🎵",
                    read_timeout=300.0,
                    write_timeout=300.0,
                    connect_timeout=60.0,
                )
        cleanup_file(file_path)

        # Automatic Music Channel Archiving (Store song in configured Telegram channel)
        try:
            from services.music_archive_service import archive_song_to_channel
            if sent_msg and sent_msg.audio:
                archive_res = await archive_song_to_channel(
                    bot=context.bot,
                    user=update.effective_user,
                    song_data={**res, "query": query},
                    sent_audio_file_id=sent_msg.audio.file_id
                )
                if archive_res and archive_res.get("success") and archive_res.get("post_url"):
                    try:
                        await sent_msg.edit_reply_markup(
                            reply_markup=InlineKeyboardMarkup([
                                [InlineKeyboardButton("📻 ស្ដាប់ក្នុង Music Channel", url=archive_res["post_url"])]
                            ])
                        )
                    except Exception:
                        pass
        except Exception as e_arch:
            logger.warning(f"Failed to auto-archive song to channel: {e_arch}")

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
            err_msg = str(e).strip() or "រកមិនឃើញបទចម្រៀង"
            await safe_edit_text(status_msg, f"❌ មិនអាចទាញយកចម្រៀងបានទេ៖ {err_msg[:150]}")

async def setsongchannel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command to set/link music storage channel: /setsongchannel <@channel or -100xxxxxxxxx>."""
    user = update.effective_user
    if not user or user.id != ADMIN_USER_ID:
        await update.message.reply_text("⛔ *ការអនុញ្ញាតត្រូវបានបដិសេធ (Admin Only)៖* ពាក្យបញ្ជានេះសម្រាប់តែម្ចាស់ Bot ប៉ុណ្ណោះ។", parse_mode="Markdown")
        return

    arg = context.args[0].strip() if context.args else ""
    if not arg:
        from database import get_music_channel
        curr = get_music_channel()
        curr_text = f"`{curr}`" if curr else "_ពុំទាន់បានកំណត់នៅឡើយទេ_"
        await update.message.reply_text(
            "📻 *ការកំណត់ Channel ផ្ទុកបទចម្រៀង (Music Channel Storage)៖*\n\n"
            f"• **Channel បច្ចុប្បន្ន៖** {curr_text}\n\n"
            "👉 *របៀបកំណត់ Channel ថ្មី៖*\n"
            "`/setsongchannel <@channel_username ឬ -100xxxxxxxx>`\n\n"
            "• **ឧទាហរណ៍៖** `/setsongchannel @my_music_channel`\n"
            "• **ឧទាហរណ៍៖** `/setsongchannel -1001234567890`\n\n"
            "💡 *ចំណាំសំខាន់៖*\n"
            "១. សូម Add Bot នេះចូលជា **Administrator** ក្នុង Channel របស់អ្នកជាមុនសិន\n"
            "២. សូមបើកសិទ្ធិ (Permission) **Post Messages** ដល់ Bot\n"
            "៣. បន្ទាប់មក រាល់ពេលដែលមានអ្នកទាញយកចម្រៀងតាម `/song` វានឹង Save ចូល Channel នោះដោយស្វ័យប្រវត្ត! 🚀",
            parse_mode="Markdown"
        )
        return

    from services.music_archive_service import verify_channel_access
    from database import set_music_channel

    status_msg = await update.message.reply_text(f"🔍 *កំពុងត្រួតពិនិត្យការតភ្ជាប់ទៅកាន់ Channel* `{arg}`... ⏳", parse_mode="Markdown")
    ok, err, info = await verify_channel_access(context.bot, arg)

    if not ok:
        await safe_edit_text(
            status_msg,
            f"❌ *មិនអាចតភ្ជាប់ទៅកាន់ Channel `{arg}` បានទេ!* ⚠️\n\n"
            f"• **មូលហេតុ៖** `{err}`\n\n"
            "🧐 *សូមពិនិត្យមើលចំណុចទាំងនេះ៖*\n"
            "១. តើអ្នកបាន Add Bot នេះចូលជា **Administrator** ក្នុង Channel រួចហើយឬនៅ?\n"
            "២. ប្រសិនបើ Channel ជា Private សូមប្រើ **Channel ID** (ឧទាហរណ៍៖ `-100xxxxxxxxxx`) ជំនួសវិញ។",
        )
        return

    set_music_channel(arg)
    ch_title = info.get("title", arg) if info else arg
    ch_id = info.get("id", arg) if info else arg
    is_admin = info.get("is_admin", False) if info else False
    can_post = info.get("can_post", False) if info else False

    admin_badge = "✅ Administrator" if is_admin else "⚠️ Not Admin (សូម Add Bot ជា Admin)"
    post_badge = "✅ Can Post Messages" if can_post else "⚠️ No Post Permission (សូមបើកសិទ្ធិ Post Messages)"

    await safe_edit_text(
        status_msg,
        f"✅ *បានកំណត់ Channel ផ្ទុកបទចម្រៀងដោយជោគជ័យ!* 🎉\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📢 *ឈ្មោះ Channel:* **{ch_title}**\n"
        f"🆔 *Channel ID / Target:* `{arg}` (`{ch_id}`)\n"
        f"🛡️ *ស្ថានភាព Bot:* {admin_badge}\n"
        f"✍️ *សិទ្ធិផុសសារ:* {post_badge}\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "💡 *ដំណើរការស្វ័យប្រវត្ត (Auto-Archive)៖*\n"
        "រាល់ពេលដែលមានអ្នកទាញយកចម្រៀងតាម `/song <ឈ្មោះបទ>` Bot នឹងផ្ញើបទចម្រៀងជូនអ្នកប្រើប្រាស់ផង "
        "និងរក្សាទុកបទចម្រៀងនោះចូលទៅក្នុង Channel នេះភ្លាមៗ (0.1s Zero-Bandwidth Instant Store)! 🎶🚀\n\n"
        "• ចុច `/songchannel` ដើម្បីពិនិត្យស្ថិតិចម្រៀងដែលបាន Save\n"
        "• ចុច `/clearsongchannel` ដើម្បីផ្ដាច់ការតភ្ជាប់",
    )

async def songchannel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """View current music storage channel status and archive stats: /songchannel."""
    from database import get_music_channel, get_music_archive_stats
    channel = get_music_channel()
    stats = get_music_archive_stats()
    total = stats.get("total_archived", 0)
    recent = stats.get("recent", [])

    lines = [
        "📻 *ស្ថានភាព Music Channel Storage (ឃ្លាំងចម្រៀងស្វ័យប្រវត្ត)៖* ✨",
        "━━━━━━━━━━━━━━━━━━━━━━",
    ]

    if channel:
        lines.append(f"📢 *Channel កំពុងភ្ជាប់៖* `{channel}` 🟢")
        lines.append(f"📦 *ចំនួនបទចម្រៀងដែលបាន Save ទុក៖* **{total} បទ**")
        lines.append("")
        if recent:
            lines.append("🕒 *បទចម្រៀងដែលបាន Save ថ្មីៗចុងក្រោយ៖*")
            for idx, r in enumerate(recent, 1):
                t = r.get("title", "Unknown")
                p = r.get("performer", "Unknown")
                lines.append(f"  {idx}. 🎵 *{t}* - _{p}_")
            lines.append("")
        lines.append("💡 *បញ្ជាគ្រប់គ្រង៖*")
        lines.append("• ប្តូរ Channel៖ `/setsongchannel <@channel>`")
        lines.append("• ផ្ដាច់ Channel៖ `/clearsongchannel`")
    else:
        lines.append("⚠️ *ពុំទាន់មាន Channel ផ្ទុកបទចម្រៀងនៅឡើយទេ!*")
        lines.append("")
        lines.append("👉 *របៀបភ្ជាប់ Channel ដើម្បី Save ចម្រៀងស្វ័យប្រវត្ត៖*")
        lines.append("១. បង្កើត Channel លើ Telegram ឬប្រើ Channel ដែលមានស្រាប់")
        lines.append("២. Add Bot នេះចូលជា **Administrator** ក្នុង Channel")
        lines.append("៣. វាយពាក្យបញ្ជា៖ `/setsongchannel @mychannel`")

    lines.append("━━━━━━━━━━━━━━━━━━━━━━")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

async def clearsongchannel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command to unlink/clear music channel storage: /clearsongchannel."""
    user = update.effective_user
    if not user or user.id != ADMIN_USER_ID:
        await update.message.reply_text("⛔ *ការអនុញ្ញាតត្រូវបានបដិសេធ (Admin Only)៖* ពាក្យបញ្ជានេះសម្រាប់តែម្ចាស់ Bot ប៉ុណ្ណោះ។", parse_mode="Markdown")
        return

    from database import remove_music_channel
    remove_music_channel()
    await update.message.reply_text(
        "🗑️ *បានផ្ដាច់ Channel ផ្ទុកបទចម្រៀងរួចរាល់!* 🛑\n\n"
        "ចាប់ពីពេលនេះទៅ រាល់បទចម្រៀងដែលទាញយកតាម `/song` នឹងត្រូវផ្ញើជូនតែអ្នកប្រើប្រាស់ប៉ុណ្ណោះ "
        "ដោយមិនមានការ Save ចូលក្នុង Channel ទៀតឡើយ។\n\n"
        "👉 ប្រសិនបើចង់ភ្ជាប់ឡើងវិញ សូមវាយ៖ `/setsongchannel <@channel>`",
        parse_mode="Markdown"
    )

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
        context.user_data["last_pdf_file_id"] = doc.file_id
        context.user_data["last_pdf_filename"] = filename

        pdf_actions_kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🔄 បម្លែងទៅ Word (.docx)", callback_data="btn_pdf_to_word"),
                InlineKeyboardButton("🗜️ បង្រួមទំហំ (Compress)", callback_data="btn_compress_pdf"),
            ],
            [
                InlineKeyboardButton("🧹 សម្អាតសារ", callback_data="btn_clean_chat"),
                InlineKeyboardButton("🔙 Menu ដើម", callback_data="btn_back_main")
            ]
        ])
        await safe_edit_text(status_msg, summary, reply_markup=pdf_actions_kb)
    except Exception as e:
        logger.error(f"Error analyzing PDF document: {e}")
        await safe_edit_text(status_msg, f"❌ កំហុសក្នុងការអាន PDF៖ {str(e)[:140]}")

# -------------------------------------------------------------
# AI Image Upscaler & Enhancer Handler
# -------------------------------------------------------------
async def enhance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Upscale and enhance image to crystal clear 2K, 4K or 8K quality: /enhance or /upscale."""
    import io
    target_msg = update.message.reply_to_message if update.message.reply_to_message else update.message
    photos = target_msg.photo if target_msg else None

    arg = (context.args[0] if context.args else "").lower().strip()
    target_mode = "4k"
    if "8k" in arg:
        target_mode = "8k"
    elif "2k" in arg:
        target_mode = "2k"
    elif "4k" in arg:
        target_mode = "4k"

    if not photos:
        await update.message.reply_text(
            "🔍 *របៀបប្រើប្រាស់ AI Image Enhancer (ធ្វើឱ្យរូបច្បាស់ 2K / 4K / 8K)៖*\n\n"
            "👉 ផ្ញើរូបភាពដោយភ្ជាប់ពាក្យ `/enhance` ឬ `/enhance 4k` ឬ `/enhance 8k`\n"
            "👉 ឬចុច **Reply** លើរូបភាពណាមួយ រួចវាយពាក្យ `/enhance` ឬ `/upscale 8k`\n\n"
            "Bot នឹងជួយសម្អាត Noise, Super-Resolution ពង្រីកដល់ 4K Ultra ឬ 8K Super-Res និងផ្ញើ File ដើមមិនបង្រួមជូនភ្លាមៗ! ✨",
            parse_mode="Markdown"
        )
        return

    photo = photos[-1]
    mode_label = "8K Super-Res" if target_mode == "8k" else ("4K Ultra" if target_mode == "4k" else "2K HD")
    await update.message.chat.send_action("upload_photo")
    status = await update.message.reply_text(f"🔍 *កំពុងដំណើរការ Super-Resolution កម្រិត {mode_label}...* ⏳", parse_mode="Markdown")

    try:
        tg_file = await context.bot.get_file(photo.file_id)
        img_bytes = bytes(await tg_file.download_as_bytearray())
        from services.image_enhancer_service import enhance_image
        enhanced_bytes, metrics = enhance_image(img_bytes, resolution_mode=target_mode)

        caption = (
            f"✨ *រូបភាពរបស់អ្នកត្រូវបានបង្កើនគុណភាព {metrics['mode']} រួចរាល់!* 🔍\n\n"
            f"📐 *ទំហំដើម:* `{metrics['orig_width']} x {metrics['orig_height']}` px\n"
            f"📈 *ទំហំថ្មី ({metrics['mode']}):* `{metrics['new_width']} x {metrics['new_height']}` px (+{metrics['scale']}x)\n"
            f"⚡ *រយៈពេលដំណើរការ:* `{metrics['elapsed_seconds']}s`"
        )

        buttons = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("💎 2K HD", callback_data="btn_upscale_2k"),
                InlineKeyboardButton("🔥 4K Ultra", callback_data="btn_upscale_4k"),
                InlineKeyboardButton("🌌 8K Super-Res", callback_data="btn_upscale_8k"),
            ],
            [
                InlineKeyboardButton("💧 ដាក់ Watermark", callback_data="btn_watermark_info"),
                InlineKeyboardButton("🔙 Menu ដើម", callback_data="btn_back_main")
            ]
        ])

        photo_to_send = metrics.get("preview_bytes") or enhanced_bytes
        await update.message.reply_photo(
            photo=io.BytesIO(photo_to_send),
            caption=caption,
            reply_markup=buttons,
            parse_mode="Markdown"
        )

        # If 4K or 8K, also send uncompressed Document so Telegram does not compress pixels
        if target_mode in ["4k", "8k"]:
            doc_io = io.BytesIO(enhanced_bytes)
            doc_io.name = f"upscaled_{target_mode}_{metrics['new_width']}x{metrics['new_height']}.jpg"
            await update.message.reply_document(
                document=doc_io,
                caption=f"📁 *ឯកសាររូបភាពដើម {metrics['mode']} មិនបង្រួម ({metrics['new_width']} x {metrics['new_height']} px)* ✨",
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
        sent = await message.reply_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
    except Exception as e:
        err_str = str(e).lower()
        if "parse entities" in err_str or "entity" in err_str:
            sent = await message.reply_text(text, reply_markup=reply_markup, parse_mode=None)
        else:
            raise
    try:
        from database import record_auto_clean_message
        record_auto_clean_message(message.chat_id, sent.message_id)
    except Exception:
        pass
    return sent

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
    """Handle voice messages using Gemini 2.5 Flash audio understanding and reply with both text & speech (Two-Way Voice Assistant)."""
    voice = update.message.voice or update.message.audio
    if not voice:
        return
        
    await update.message.chat.send_action("typing")
    status = await update.message.reply_text("🎙️ *កំពុងស្តាប់ និងវិភាគសារសំឡេងរបស់អ្នក (Two-Way Voice Assistant)...* 🎧", parse_mode="Markdown")
    
    try:
        tg_file = await context.bot.get_file(voice.file_id)
        voice_bytes = await tg_file.download_as_bytearray()
        
        # Check if caption or audio is a song identification request
        caption = update.message.caption or ""
        if any(k in caption.lower() for k in ["/shazam", "/identify", "ចម្រៀង", "បទអ្វី", "song", "shazam"]):
            shazam_res = await identify_song_from_audio(bytes(voice_bytes), mime_type="audio/ogg")
            await safe_edit_text(status, shazam_res)
            return

        reply_text = await process_voice_ai(bytes(voice_bytes), mime_type="audio/ogg")
        await safe_edit_text(status, reply_text)

        # Two-Way Voice Assistant: Synthesize speech in Khmer and reply with voice audio ONLY on successful answers
        if not reply_text.startswith("❌") and not reply_text.startswith("⚠️"):
            try:
                from services.tts_service import generate_tts_audio
                clean_reply = re.sub(r"[*_`#~\[\]()>]", "", reply_text).strip()
                if clean_reply and len(clean_reply) <= 600:
                    audio_fp = generate_tts_audio(clean_reply, lang="km")
                    await update.message.reply_voice(
                        voice=audio_fp,
                        caption="🗣️ *ឆ្លើយតបជាសំឡេង AI (Two-Way Voice)* ✨"
                    )
            except Exception as e_voice:
                logger.warning(f"Could not send voice reply: {e_voice}")

    except Exception as e:
        logger.error(f"Error handling voice message: {e}")
        await safe_edit_text(status, f"❌ មិនអាចដំណើរការសារជាសំឡេងបានទេ៖ {str(e)[:100]}")

async def handle_photo_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle photo messages: automatically extract location directly from image (EXIF GPS or AI Geolocation), or handle QR / Vision."""
    import re
    photos = update.message.photo
    if not photos:
        return
        
    # Get highest resolution
    photo = photos[-1]
    caption = update.message.caption or ""
    caption_lower = caption.lower()
    
    await update.message.chat.send_action("typing")
    
    try:
        tg_file = await context.bot.get_file(photo.file_id)
        img_bytes = bytes(await tg_file.download_as_bytearray())
        context.user_data["last_photo_bytes"] = img_bytes

        # Check if caption requests Word or Excel conversion
        if any(k in caption_lower for k in ["/word", "/docx", "word", "docx", "បម្លែងជា word"]):
            status = await update.message.reply_text("📝 *កំពុងស្កេន OCR និងបម្លែងរូបភាពជាឯកសារ Word (.docx)...*", parse_mode="Markdown")
            await update.message.chat.send_action("upload_document")
            from services.doc_converter_service import convert_image_to_docx
            import io
            docx_bytes, filename, summary = await convert_image_to_docx(img_bytes)
            if docx_bytes:
                await update.message.reply_document(
                    document=io.BytesIO(docx_bytes),
                    filename=filename,
                    caption=f"📝 *បានបម្លែងជា Word (.docx) ជោគជ័យ!* ✨\n\n_{summary}_\n\n🤖 Smart Assistant Bot 🚀",
                    parse_mode="Markdown"
                )
                try:
                    await status.delete()
                except Exception:
                    pass
                return

        if any(k in caption_lower for k in ["/excel", "/sheet", "/xlsx", "excel", "sheet", "xlsx", "បម្លែងជា excel"]):
            status = await update.message.reply_text("📊 *កំពុងស្កេនតារាង និងបម្លែងរូបភាពជា Excel (.xlsx)...*", parse_mode="Markdown")
            await update.message.chat.send_action("upload_document")
            from services.doc_converter_service import convert_image_to_xlsx
            import io
            xlsx_bytes, filename, summary = await convert_image_to_xlsx(img_bytes)
            if xlsx_bytes:
                await update.message.reply_document(
                    document=io.BytesIO(xlsx_bytes),
                    filename=filename,
                    caption=f"📊 *បានបម្លែងជា Excel (.xlsx) ជោគជ័យ!* ✨\n\n_{summary}_\n\n🤖 Smart Assistant Bot 🚀",
                    parse_mode="Markdown"
                )
                try:
                    await status.delete()
                except Exception:
                    pass
                return
        
        # 1. First priority: Check for hardware EXIF GPS metadata in photo
        gps_coords = extract_gps_from_image_bytes(img_bytes)

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

        # Check if caption explicitly requests Song / Music recognition & download
        is_song_request = any(k in caption_lower for k in [
            "/song", "/music", "រកចម្រៀង", "រកបទ", "ទាញយកចម្រៀង", "ចម្រៀង", "song"
        ])
        if is_song_request:
            extra_hint = re.sub(r'/(song|music)|(រកចម្រៀង|រកបទ|ទាញយកចម្រៀង|ចម្រៀង|song)', '', caption, flags=re.IGNORECASE).strip()
            status = await update.message.reply_text("🖼️ *បានទទួលរូបភាព! AI កំពុងស្កេនរកឈ្មោះបទចម្រៀងពីរូបភាព...* 🔍🎶", parse_mode="Markdown")
            from services.music_service import extract_song_query_from_image, download_song
            extracted_query = await extract_song_query_from_image(img_bytes, extra_hint=extra_hint)
            if not extracted_query:
                await safe_edit_text(status, "❌ មិនអាចស្គាល់ឈ្មោះបទចម្រៀងពីរូបភាពនេះបានទេ។ សូមសាកល្បងវាយ `/song <ឈ្មោះបទ>` ដោយផ្ទាល់។")
                return

            await safe_edit_text(status, f"🔍 *បានស្កេនឃើញបទ៖* `{extracted_query}` 🎶\n_កំពុងទាញយក file MP3 កម្រិតច្បាស់..._")
            await update.message.chat.send_action("upload_voice")

            from services.video_downloader import cleanup_file
            try:
                res = await download_song(extracted_query)
                file_path = res["file_path"]
                dur = int(res.get("duration", 0) or 0)
                await safe_edit_text(status, f"📤 *ទាញយកបានសម្រេច!* កំពុងផ្ញើបទ `{res['title'][:35]}` ទៅ Telegram... 🎶")

                caption_html = (
                    f"🎧 <b>{html.escape(res['title'])}</b>\n"
                    f"👤 <b>តារាចម្រៀង:</b> {html.escape(res['performer'])}\n"
                    f"⏱️ <b>រយៈពេល:</b> {res['duration_str']}\n"
                    f"📸 <i>(ស្កេនដោយ AI ពីរូបភាព)</i>\n\n"
                    f"✨ Smart Assistant Bot 🎵"
                )
                sent_msg = None
                with open(file_path, "rb") as audio_file:
                    try:
                        sent_msg = await update.message.reply_audio(
                            audio=audio_file,
                            title=res["title"],
                            performer=res["performer"],
                            duration=dur,
                            caption=caption_html,
                            parse_mode="HTML",
                            read_timeout=300.0,
                            write_timeout=300.0,
                            connect_timeout=60.0,
                        )
                    except Exception:
                        audio_file.seek(0)
                        sent_msg = await update.message.reply_audio(
                            audio=audio_file,
                            title=res["title"],
                            performer=res["performer"],
                            duration=dur,
                            caption=f"🎧 {res['title']}\n👤 {res['performer']}\n⏱️ {res['duration_str']}\n\n✨ Smart Assistant Bot 🎵",
                        )
                cleanup_file(file_path)

                # Automatic Music Channel Archiving (@Song182)
                try:
                    from services.music_archive_service import archive_song_to_channel
                    if sent_msg and sent_msg.audio:
                        archive_res = await archive_song_to_channel(
                            bot=context.bot,
                            user=update.effective_user,
                            song_data={**res, "query": extracted_query},
                            sent_audio_file_id=sent_msg.audio.file_id
                        )
                        if archive_res and archive_res.get("success") and archive_res.get("post_url"):
                            try:
                                await sent_msg.edit_reply_markup(
                                    reply_markup=InlineKeyboardMarkup([
                                        [InlineKeyboardButton("📻 ស្ដាប់ក្នុង Music Channel", url=archive_res["post_url"])]
                                    ])
                                )
                            except Exception:
                                pass
                except Exception as e_arch:
                    logger.warning(f"Failed to auto-archive song from photo: {e_arch}")

                try:
                    import shutil
                    shutil.rmtree(res["temp_dir"], ignore_errors=True)
                    await status.delete()
                except Exception:
                    pass
                return
            except asyncio.TimeoutError:
                logger.warning(f"Song from photo download timeout for query: {extracted_query}")
                await safe_edit_text(status, "❌ ការទាញយកចម្រៀងលើសម៉ោងកំណត់ (Timeout)។ សូមសាកល្បងម្ដងទៀត ឬវាយ `/song <ឈ្មោះបទ>` ដោយផ្ទាល់។")
                return
            except Exception as e_dl:
                logger.error(f"Song from photo download error: {e_dl}")
                err_msg = str(e_dl).strip() or "រកមិនឃើញបទចម្រៀង"
                await safe_edit_text(status, f"❌ មិនអាចទាញយកចម្រៀងបានទេ៖ {err_msg[:150]}")
                return

        # Check if caption explicitly requests AI Content Creator Studio (Facebook/TikTok)
        if any(k in caption_lower for k in ["/caption", "/content", "/post", "/script", "caption", "សរសេរ caption", "ផុសលក់"]):
            status = await update.message.reply_text("🎬 *AI កំពុងវិភាគរូបភាពផលិតផល និងរៀបចំ Caption លក់ & Script TikTok...* ⏳", parse_mode="Markdown")
            from services.content_creator_service import generate_social_content, format_content_card
            topic = caption.replace("/caption", "").replace("/content", "").replace("/post", "").replace("/script", "").strip() or "ផលិតផលក្នុងរូបភាព"
            content_data = await generate_social_content(topic=topic, image_bytes=img_bytes)
            context.user_data["last_content_data"] = content_data
            card_text = format_content_card(content_data, view_mode="all")
            await safe_edit_text(status, card_text, reply_markup=get_content_keyboard("all"))
            return

        # Check if caption explicitly requests car dashboard diagnostic
        if any(k in caption_lower for k in ["/car", "/dashboard", "/diagnostic", "កុងទ័រ", "ឡាន", "ភ្លើងឡាន", "រថយន្ត", "check engine", "obd"]):
            status = await update.message.reply_text("🔧 *កំពុងវិភាគភ្លើងសញ្ញាកុងទ័ររថយន្ត (Car Diagnostic AI)...* ⏳", parse_mode="Markdown")
            diag_report = await diagnose_car_dashboard(img_bytes, caption=caption)
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("🚗 គណនាការធ្វើដំណើរ (/trip)", callback_data="btn_trip_menu")],
                [InlineKeyboardButton("🔙 Menu ដើម", callback_data="btn_back_main")]
            ])
            await safe_edit_text(status, diag_report, reply_markup=kb)
            return

        # Check if caption explicitly requests receipt/bill scanning OR mentions budget/spend keywords
        is_receipt_request = any(k in caption_lower for k in [
            "/receipt", "/bill", "/invoice", "វិក្កយបត្រ", "ស្លីប", "បង្កាន់ដៃ",
            "ចំណាយ", "ទិញ", "ហាង", "spend", "bought", "aba", "bakong", "wing"
        ])
        if is_receipt_request:
            status = await update.message.reply_text("🧾 *កំពុងអាន និងស្កេនវិក្កយបត្រ (AI Receipt Scanner)...* ⏳", parse_mode="Markdown")
            parsed_receipt = await scan_receipt_image(img_bytes, caption=caption)
            if parsed_receipt.get("is_receipt"):
                rec_msg = record_receipt_transaction(update.effective_chat.id, parsed_receipt)
                kb = InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton("📊 របាយការណ៍ចំណាយ", callback_data="btn_budget"),
                        InlineKeyboardButton("📈 ក្រាហ្វិក (Pie Chart)", callback_data="btn_budget_chart")
                    ],
                    [InlineKeyboardButton("🔙 Menu ដើម", callback_data="btn_back_main")]
                ])
                await safe_edit_text(status, rec_msg, reply_markup=kb)
                return
            else:
                await safe_edit_text(status, "⚠️ រូបភាពនេះមិនមែនជាវិក្កយបត្រ ឬស្លីបបង់ប្រាក់ទេ។ AI នឹងវិភាគទីតាំងជូនជំនួសវិញ... 🛰️")

        # Check if caption explicitly requests image enhancement (HD Upscaler)
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

        # Check if caption explicitly requests watermark
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

        # Check if caption explicitly requests background removal
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

        # Check if it's a QR code / KHQR payment receipt
        qr_text = read_qr_code(img_bytes)
        if qr_text and (not caption or any(k in caption_lower for k in ["qr", "khqr", "ស្កេន", "scan"])):
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

        # Check if caption explicitly requests OCR / homework solving / text translation
        is_ocr_request = any(k in caption_lower for k in [
            "បកប្រែ", "translate", "អានអក្សរ", "ដោះស្រាយ", "លំហាត់", "សង្ខេប", "ocr", "អានឯកសារ"
        ])
        if is_ocr_request:
            status = await update.message.reply_text("📷 *AI កំពុងអាន និងដោះស្រាយរូបភាពរបស់អ្នក...* 🔍", parse_mode="Markdown")
            reply_text = await process_vision_ai(img_bytes, mime_type="image/jpeg", caption=caption)
            photo_action_kb = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("📍 ស្វែងរកទីតាំង (GPS)", callback_data="btn_photo_loc_help"),
                    InlineKeyboardButton("🔍 ធ្វើឱ្យច្បាស់ HD", callback_data="btn_photo_enhance_help"),
                ],
                [
                    InlineKeyboardButton("🔙 Menu ដើម", callback_data="btn_back_main"),
                ]
            ])
            await safe_edit_text(status, reply_text, reply_markup=photo_action_kb)
            return

        # 2. DEFAULT BEHAVIOR: Automatically extract location directly from the image!
        # "ចង់ឲពេលsend image ឲវាទាញយកlocation ពីក្នុង image តែម្តង"
        status = await update.message.reply_text("📍 *កំពុងទាញយក និងវិភាគទីតាំងពីរូបភាព (AI Geolocation)...* 🛰️", parse_mode="Markdown")
        vision_loc = await identify_location_via_vision(img_bytes, caption=caption)
        
        maps_url = extract_maps_url_from_vision_text(vision_loc)
        buttons = []
        if maps_url:
            buttons.append([InlineKeyboardButton("🗺️ បើកមើលលើ Google Maps", url=maps_url)])
        buttons.append([
            InlineKeyboardButton("📝 បម្លែង Word (.docx)", callback_data="btn_photo_to_docx"),
            InlineKeyboardButton("📊 បម្លែង Excel (.xlsx)", callback_data="btn_photo_to_xlsx"),
        ])
        buttons.append([
            InlineKeyboardButton("🔍 ធ្វើឱ្យច្បាស់ HD", callback_data="btn_photo_enhance_help"),
            InlineKeyboardButton("🧹 សម្អាតសារ", callback_data="btn_clean_chat")
        ])
        buttons.append([
            InlineKeyboardButton("🔙 Menu ដើម", callback_data="btn_back_main")
        ])
        
        await safe_edit_text(status, vision_loc, reply_markup=InlineKeyboardMarkup(buttons))

        # If estimated coordinates in Cambodia were found, send native Telegram map pin
        coords_match = re.search(r"(\d{1,2}\.\d{3,8})[,\s]+(\d{2,3}\.\d{3,8})", vision_loc)
        if coords_match:
            try:
                plat, plon = float(coords_match.group(1)), float(coords_match.group(2))
                if 9.0 <= plat <= 15.5 and 102.0 <= plon <= 108.0:
                    await update.message.reply_location(latitude=plat, longitude=plon)
            except Exception as e_loc:
                logger.debug(f"Could not reply estimated location pin: {e_loc}")
        
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
        caption_lower = caption.lower()

        # 1. Check for hardware EXIF GPS
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

        # 2. Check explicit commands on document image
        if "/enhance" in caption_lower or "/upscale" in caption_lower or "ច្បាស់" in caption_lower:
            status = await update.message.reply_text("🔍 *កំពុងបង្កើនគុណភាពរូបភាព HD...* ⏳", parse_mode="Markdown")
            import io
            enhanced_bytes, metrics = enhance_image(img_bytes)
            caption_out = (
                f"✨ *រូបភាពរបស់អ្នកត្រូវបានបង្កើនគុណភាព HD រួចរាល់!* 🔍\n\n"
                f"📐 *ទំហំដើម:* `{metrics['orig_width']} x {metrics['orig_height']}` px\n"
                f"📈 *ទំហំថ្មី (HD):* `{metrics['new_width']} x {metrics['new_height']}` px (+{metrics['scale']}x)"
            )
            await update.message.reply_photo(photo=io.BytesIO(enhanced_bytes), caption=caption_out, parse_mode="Markdown")
            try:
                await status.delete()
            except Exception:
                pass
            return

        if "/rembg" in caption_lower or "កាត់" in caption_lower or "background" in caption_lower:
            status = await update.message.reply_text("✂️ *កំពុងកាត់ផ្ទៃខាងក្រោយ...*", parse_mode="Markdown")
            png_fp = await remove_background(img_bytes)
            png_fp.name = "cutout.png"
            await update.message.reply_document(document=png_fp, caption="✂️ *កាត់ផ្ទៃខាងក្រោយជោគជ័យ!*", parse_mode="Markdown")
            try:
                await status.delete()
            except Exception:
                pass
            return

        is_ocr_request = any(k in caption_lower for k in [
            "បកប្រែ", "translate", "អានអក្សរ", "ដោះស្រាយ", "លំហាត់", "សង្ខេប", "ocr"
        ])
        if is_ocr_request:
            status = await update.message.reply_text("📷 *AI កំពុងអានឯកសាររូបភាពរបស់អ្នក...* 🔍", parse_mode="Markdown")
            reply_text = await process_vision_ai(img_bytes, mime_type="image/jpeg", caption=caption)
            await safe_edit_text(status, reply_text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu ដើម", callback_data="btn_back_main")]]))
            return

        # 3. DEFAULT: Automatically extract location from document image!
        status = await update.message.reply_text("📍 *កំពុងទាញយក និងវិភាគទីតាំងពីរូបភាព File (AI Geolocation)...* 🛰️", parse_mode="Markdown")
        vision_loc = await identify_location_via_vision(img_bytes, caption=caption)
        maps_url = extract_maps_url_from_vision_text(vision_loc)
        buttons = []
        if maps_url:
            buttons.append([InlineKeyboardButton("🗺️ បើកមើលលើ Google Maps", url=maps_url)])
        buttons.append([
            InlineKeyboardButton("🧹 សម្អាតសារ", callback_data="btn_clean_chat"),
            InlineKeyboardButton("🔙 Menu ដើម", callback_data="btn_back_main")
        ])
        await safe_edit_text(status, vision_loc, reply_markup=InlineKeyboardMarkup(buttons))

        # If estimated coordinates in Cambodia were found, send native Telegram map pin
        coords_match = re.search(r"(\d{1,2}\.\d{3,8})[,\s]+(\d{2,3}\.\d{3,8})", vision_loc)
        if coords_match:
            try:
                plat, plon = float(coords_match.group(1)), float(coords_match.group(2))
                if 9.0 <= plat <= 15.5 and 102.0 <= plon <= 108.0:
                    await update.message.reply_location(latitude=plat, longitude=plon)
            except Exception as e_loc:
                logger.debug(f"Could not reply estimated location pin: {e_loc}")

    except Exception as e:
        logger.error(f"Error handling document image: {e}")

async def handle_user_video_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle user-uploaded video, video note, or animation: extract location (Video Geolocation) or tools."""
    video = update.message.video or update.message.animation or update.message.video_note
    if not video:
        return

    caption = update.message.caption or ""
    caption_lower = caption.lower()

    await update.message.chat.send_action("typing")

    try:
        # 1. Check if caption requests MP3 audio extraction
        if any(k in caption_lower for k in ["/mp3", "mp3", "ចម្រៀង", "audio", "សំឡេង"]):
            status = await update.message.reply_text("🎵 *កំពុងទាញយកសំឡេង MP3 ចេញពីវីដេអូ...* ⏳", parse_mode="Markdown")
            tg_file = await context.bot.get_file(video.file_id)
            vid_bytes = bytes(await tg_file.download_as_bytearray())
            from services.file_master_service import video_to_mp3_bytes
            mp3_bytes, mp3_stats = video_to_mp3_bytes(vid_bytes)
            import io
            await update.message.reply_audio(
                audio=io.BytesIO(mp3_bytes),
                title="Audio from Video",
                performer="Telegram Assistant Bot",
                caption=f"🎵 *ទាញយក MP3 ជោគជ័យ!* (`{mp3_stats['mp3_size_kb']} KB`)",
                parse_mode="Markdown"
            )
            try:
                await status.delete()
            except Exception:
                pass
            return

        # 2. DEFAULT BEHAVIOR: Extract and identify location from the video (Video Geolocation AI)!
        status = await update.message.reply_text("📍 *កំពុងទាញយក និងវិភាគទីតាំងក្នុងវីដេអូ (Video Geolocation AI)...* 🛰️", parse_mode="Markdown")

        media_bytes = None
        mime_type = "video/mp4"

        file_size = getattr(video, "file_size", 0) or 0
        if file_size and file_size <= 20 * 1024 * 1024:
            try:
                tg_file = await context.bot.get_file(video.file_id)
                media_bytes = bytes(await tg_file.download_as_bytearray())
                mime_type = getattr(video, "mime_type", None) or "video/mp4"
            except Exception as e_dl:
                logger.warning(f"Could not download full video for vision: {e_dl}")

        # Fallback to video thumbnail if full video is too large or download failed
        if not media_bytes:
            thumb = getattr(video, "thumbnail", None) or getattr(video, "thumb", None)
            if thumb:
                try:
                    tg_thumb = await context.bot.get_file(thumb.file_id)
                    media_bytes = bytes(await tg_thumb.download_as_bytearray())
                    mime_type = "image/jpeg"
                except Exception as e_th:
                    logger.warning(f"Could not download video thumbnail: {e_th}")

        if not media_bytes:
            await safe_edit_text(status, "❌ មិនអាចទាញយកទិន្នន័យពីវីដេអូនេះបានទេ (ទំហំធំលើសកំណត់ >20MB)។ សូមសាកល្បងថតជារូបភាពផ្ញើមកវិញណា៎!")
            return

        vision_loc = await identify_location_via_vision(media_bytes, caption=caption, mime_type=mime_type)

        maps_url = extract_maps_url_from_vision_text(vision_loc)
        buttons = []
        if maps_url:
            buttons.append([InlineKeyboardButton("🗺️ បើកមើលលើ Google Maps", url=maps_url)])
        buttons.append([
            InlineKeyboardButton("🧹 សម្អាតសារ", callback_data="btn_clean_chat"),
            InlineKeyboardButton("🔙 Menu ដើម", callback_data="btn_back_main")
        ])

        await safe_edit_text(status, vision_loc, reply_markup=InlineKeyboardMarkup(buttons))

        # If estimated coordinates in Cambodia were found, send native Telegram map pin
        coords_match = re.search(r"(\d{1,2}\.\d{3,8})[,\s]+(\d{2,3}\.\d{3,8})", vision_loc)
        if coords_match:
            try:
                plat, plon = float(coords_match.group(1)), float(coords_match.group(2))
                if 9.0 <= plat <= 15.5 and 102.0 <= plon <= 108.0:
                    await update.message.reply_location(latitude=plat, longitude=plon)
            except Exception as e_loc:
                logger.debug(f"Could not reply estimated location pin from video: {e_loc}")

    except Exception as e:
        logger.error(f"Error handling video message: {e}")
        await safe_reply_text(update.message, f"❌ កំហុសក្នុងការដំណើរការវីដេអូ៖ {str(e)[:100]}")

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
        "🔹 `/briefing` - សង្ខេបព័ត៌មាន VIP រាល់ព្រឹក\n"
        "🔹 `/listen <url>` - បម្លែងអត្ថបទ Web ជា Audio Podcast\n"
        "🔹 `/chord <បទ>` - រកបន្ទះ Chord ហ្គីតា/ព្យាណូ\n"
        "🔹 `/chart` - មើលក្រាហ្វិកចំណាយ Donut/Pie Chart\n"
        "🔹 `/excel` - ទាញយកប្រវត្តិចំណាយជា Excel (.xlsx)\n"
        "🔹 `/budget` - មើលរបាយការណ៍ចំណូល-ចំណាយ\n"
        "🔹 `/finance` - មើលអត្រាប្តូរប្រាក់ តម្លៃមាស និងតម្លៃសាំង\n"
        "🔹 `/trip <ខេត្ត>` - គណនាការធ្វើដំណើរ & ថ្លៃសាំង\n"
        "🔹 `/code` - Code Runner & Debugger ក្នុង Telegram\n"
        "🔹 `/compress` - បង្រួម & បម្លែងឯកសារ (File Master)\n"
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
        "🔹 `/user <username>` - ស្វែងរក & បង្កើត Link ឆាតទៅកាន់ Profile\n"
        "🔹 `/crypto` - តាមដានតម្លៃ Crypto, TON & មាស Live\n"
        "🔹 `/alert <coin> <price>` - កំណត់ម៉ោងរោទ៍ Alert តម្លៃកាក់ (Drop/Pump)\n"
        "🔹 `/alerts` - មើល & ចាត់ចែង Price Alerts សកម្មរបស់អ្នក\n"
        "🔹 `/status` - ពិនិត្យស្ថានភាពគណនី\n\n"
        "📸 *Receipt Scanner:* ថតរូបវិក្កយបត្រ ឬស្លីបបង់ប្រាក់ ➔ AI កត់ចំណាយស្វ័យប្រវត្តិ!\n"
        "🗣️ *Voice Assistant:* ផ្ញើសារសំឡេង Voice Note ➔ Bot ឆ្លើយតបជាសំឡេងនិយាយខ្មែរ!\n"
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

    # Delegate media download callbacks (MP3, HD Cover, 1080p, 4K, 8K, AI Summary, Subtitles)
    if data.startswith("dlmp3_") or data.startswith("dlthumb_") or data.startswith("dlqual_") or data.startswith("dlsum_") or data.startswith("dlsub_"):
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
                        InlineKeyboardButton("📊 ក្រាហ្វិក (Pie Chart)", callback_data="btn_budget_chart"),
                        InlineKeyboardButton("📥 ទាញយក Excel (.xlsx)", callback_data="btn_budget_excel"),
                    ],
                    [
                        InlineKeyboardButton("🧾 របៀបស្កេនវិក្កយបត្រ", callback_data="btn_scan_receipt_help"),
                        InlineKeyboardButton("🔄 ធ្វើបច្ចុប្បន្នភាព", callback_data="btn_budget"),
                    ],
                    [
                        InlineKeyboardButton("🗑️ សម្អាតប្រវត្តិ", callback_data="btn_clear_expenses_ask"),
                        InlineKeyboardButton("🔙 Menu ដើម", callback_data="btn_back_main")
                    ]
                ]),
                parse_mode="Markdown"
            )

        elif data == "btn_budget_chart":
            await query.answer("📊 កំពុងបង្កើតក្រាហ្វិក Pie Chart...")
            chart_bytes = generate_budget_pie_chart(chat_id)
            if chart_bytes:
                import io
                await context.bot.send_photo(
                    chat_id=chat_id,
                    photo=io.BytesIO(chart_bytes),
                    caption="📊 *ក្រាហ្វិកវិភាគចំណាយតាមប្រភេទ (Donut / Pie Chart - 30 ថ្ងៃ)* ✨\n💡 _លោកអ្នកអាចចុច /excel ដើម្បីទាញយកតារាង Excel ពេញលេញ_",
                    parse_mode="Markdown"
                )
            else:
                await query.answer("⚠️ មិនទាន់មានទិន្នន័យចំណាយសម្រាប់គូសក្រាហ្វិកនៅឡើយទេ។", show_alert=True)

        elif data == "btn_budget_excel":
            await query.answer("📥 កំពុងរៀបចំឯកសារ Excel (.xlsx)...")
            excel_bytes = generate_budget_excel(chat_id)
            import io
            today_str = datetime.now().strftime("%Y-%m-%d")
            await context.bot.send_document(
                chat_id=chat_id,
                document=io.BytesIO(excel_bytes),
                filename=f"budget_history_{today_str}.xlsx",
                caption=f"📈 *ឯកសារប្រវត្តិចំណូល-ចំណាយ Excel (.xlsx)*\n📅 កាលបរិច្ឆេទ៖ `{today_str}`\n💡 _បើកមើលលើ Excel, Google Sheets ឬ Numbers_",
                parse_mode="Markdown"
            )

        elif data == "btn_scan_receipt_help":
            await query.answer()
            help_msg = (
                "🧾 *របៀបប្រើប្រាស់ AI Receipt Scanner (ស្កេនវិក្កយបត្រស្វ័យប្រវត្តិ)៖* 📸\n\n"
                "1. **ថតរូបវិក្កយបត្រ** ភោជនីយដ្ឋាន, ផ្សារទំនើប (AEON, Lucky, Chip Mong...) ឬស្លីបបង់ប្រាក់ ABA / Bakong / Wing\n"
                "2. **ផ្ញើរូបភាពចូលមកក្នុង Bot នេះភ្លាមៗ**\n"
                "   • _(អាចដាក់ Caption ថា `វិក្កយបត្រ`, `ស្លីប`, `/receipt` ឬផ្ញើតែរូបភាពក៏បាន)_\n"
                "3. AI Vision នឹងស្កេនទាញយក៖\n"
                "   • 🏪 ឈ្មោះហាង / ស្ថាប័ន\n"
                "   • 💵 ចំនួនទឹកប្រាក់ ($ ឬ ៛)\n"
                "   • 📅 កាលបរិច្ឆេទ\n"
                "   • 🛒 មុខទំនិញលម្អិត\n"
                "4. Bot នឹងកត់ចូលប្រព័ន្ធ `/budget` ដោយស្វ័យប្រវត្តិតែម្តង! 🚀"
            )
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("📊 ពិនិត្យមើលចំណាយ (/budget)", callback_data="btn_budget")],
                [InlineKeyboardButton("🔙 Menu ដើម", callback_data="btn_back_main")]
            ])
            await query.edit_message_text(help_msg, reply_markup=kb, parse_mode="Markdown")

        elif data == "btn_podcast_help":
            await query.answer()
            tip = (
                "🎧 *Web Article to Audio Podcast (បម្លែងអត្ថបទវេបសាយជាសំឡេង)៖* 🎙️\n\n"
                "👉 *របៀបប្រើប្រាស់៖*\n"
                "• វាយ `/listen <Link វេបសាយព័ត៌មាន ឬអត្ថបទ>`\n"
                "• ឬ `/podcast <Link>`\n\n"
                "• ឧទាហរណ៍៖\n"
                "`/listen https://freshnewsasia.com/...`\n\n"
                "✨ *សមត្ថភាពពិសេស៖*\n"
                "1. ស្រង់ខ្លឹមសារអត្ថបទដោយស្វ័យប្រវត្តិពីវេបសាយ\n"
                "2. សង្ខេប ៣ ចំណុចសំខាន់ៗជាភាសាខ្មែរផ្លូវការ\n"
                "3. បង្កើតជា File សំឡេង (Khmer Audio Podcast .mp3) អានខ្លឹមសារនោះឱ្យលោកអ្នកស្តាប់ភ្លាមៗ! 📻"
            )
            await query.edit_message_text(tip, reply_markup=get_back_keyboard(), parse_mode="Markdown")

        elif data == "btn_chord_help":
            await query.answer()
            tip = (
                "🎸 *Guitar / Piano Chord Finder & Shazam តន្ត្រី៖* 🎵\n\n"
                "👉 *១. រកបន្ទះ Chord ចម្រៀងខ្មែរ & អន្តរជាតិ៖*\n"
                "• វាយ `/chord <ឈ្មោះបទ ឬអ្នកច្រៀង>`\n"
                "• ឧទាហរណ៍៖ `/chord ចិត្តអើយ` ឬ `/chord perfect ed sheeran`\n"
                "• បង្ហាញ Key, Tempo, Strumming Pattern, Capo និងទំនុកច្រៀងអមបន្ទះ Chord ត្រឹមត្រូវសម្រាប់លេងហ្គីតា/ព្យាណូ!\n\n"
                "👉 *២. ស្គាល់បទភ្លេង (Shazam Song Identifier)៖*\n"
                "• ឮគេចាក់បទភ្លេងពិរោះនៅហាងកាហ្វេ គ្រាន់តែថត **Voice Note** សំឡេងបទនោះ ៥-១០ វិនាទី ផ្ញើមក Bot\n"
                "• ឬផ្ញើសំឡេងដោយដាក់ Caption ថា `/shazam` ឬ `ចម្រៀង`\n"
                "• AI នឹងប្រាប់ឈ្មោះបទ ឈ្មោះអ្នកច្រៀង និងអត្ថបទចម្រៀងភ្លាមៗ! 🎶"
            )
            await query.edit_message_text(tip, reply_markup=get_back_keyboard(), parse_mode="Markdown")

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
                "👤 *៣. Telegram Profile Resolver (ស្វែងរកគណនី)៖*\n"
                "• វាយ `/user <username>` ឬ `/whois <username>`\n"
                "• បង្កើត Link ឆាតទៅកាន់ Profile ភ្លាមៗមួយចុច (1-Click Chat)!\n\n"
                "🎙️ *៤. ជជែកជាសំឡេង (Voice AI)៖*\n"
                "• គ្រាន់តែសង្កត់ផ្ញើសារសំឡេង Voice Note នោះ AI នឹងឆ្លើយតបមកវិញ\n\n"
                "📄 *៥. Vision AI & OCR៖*\n"
                "• ផ្ញើរូបភាពឯកសារ វិក្កយបត្រ ឬលំហាត់ ➔ AI ជួយអាន និងដោះស្រាយ"
            )
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("👤 ស្វែងរកគណនី (/user)", callback_data="btn_user_help")],
                [InlineKeyboardButton("🔙 Menu ដើម", callback_data="btn_back_main")]
            ])
            await query.edit_message_text(tools_msg, reply_markup=kb, parse_mode="Markdown")

        elif data == "btn_user_help":
            await query.answer()
            _, _, tip = validate_username_format("")
            await query.edit_message_text(tip, reply_markup=get_back_keyboard(), parse_mode="Markdown")

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
                "✨ *ជំនួយការឆ្លាតវៃ AI (Gemini Flash & GPT - Master Level)* 🤖\n\n"
                "លោកអ្នកអាចសួរនាំសំណួរ វិភាគទិន្នន័យ បកប្រែភាសា និងសរសេរអត្ថបទបានយ៉ាងរហ័ស!\n\n"
                "💡 *មុខងារពិសេសៗកម្រិត Master៖*\n"
                f"• **AI Continuous Chat:** {'✅ កំពុងបើក' if ai_active else '❌ បានបិទ'} (ជជែកជាប់គ្នាដោយមិនបាច់វាយ /ask)\n"
                "• **🧠 Long-Term Memory:** ចងចាំចំណូលចិត្តតន្ត្រី និងទម្លាប់របស់អ្នកស្វ័យប្រវត្តិ\n"
                "• **🌐 Real-Time Search:** ស្វែងរកព័ត៌មានផ្ទាល់ពី Google Search Grounding (`/search`)\n"
                "• **🎙️ Voice Message AI:** ផ្ញើសារសំឡេង Voice ➔ AI ឆ្លើយតបជាសំឡេង/អក្សរ\n"
                "• **📷 Vision OCR:** ផ្ញើរូបភាព ➔ AI អានអក្សរ បកប្រែ ឬដោះស្រាយលំហាត់\n"
                "• **Commands:** `/ask <សំណួរ>`, `/search <ពាក្យស្វែងរក>`, `/memory`"
            )
            keyboard = [
                [InlineKeyboardButton("💬 បើក/បិទ AI Continuous Chat", callback_data="btn_toggle_aimode")],
                [
                    InlineKeyboardButton("🧠 ការចងចាំ (/memory)", callback_data="btn_view_memory"),
                    InlineKeyboardButton("🌐 ស្វែងរក Live (/search)", callback_data="btn_search_help")
                ],
                [InlineKeyboardButton("🗑️ សម្អាត Conversation Memory", callback_data="btn_clear_aimem")],
                [InlineKeyboardButton("🔙 Menu ដើម", callback_data="btn_back_main")]
            ]
            await query.edit_message_text(ai_msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

        elif data == "btn_view_memory":
            await query.answer()
            from services.memory_service import format_user_memory_display
            mem_text = format_user_memory_display(chat_id)
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("🗑️ លុបការចងចាំទាំងអស់", callback_data="btn_clear_longterm_memory")],
                [InlineKeyboardButton("🔙 ត្រឡប់ទៅ AI Menu", callback_data="btn_ai_menu")]
            ])
            await query.edit_message_text(mem_text, reply_markup=kb, parse_mode="Markdown")

        elif data == "btn_clear_longterm_memory":
            from database import clear_user_memories
            from services.cache_service import cache_delete
            clear_user_memories(chat_id)
            cache_delete(f"mem_prompt_{chat_id}")
            await query.answer("✅ បានលុបការចងចាំ Long-Term Memory ទាំងអស់រួចរាល់!", show_alert=True)
            from services.memory_service import format_user_memory_display
            await query.edit_message_text(
                format_user_memory_display(chat_id),
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 ត្រឡប់ទៅ AI Menu", callback_data="btn_ai_menu")]]),
                parse_mode="Markdown"
            )

        elif data == "btn_search_help":
            await query.answer()
            search_msg = (
                "🌐 *ស្វែងរកព័ត៌មាន Real-Time ជាមួយ Google Search Grounding* 🔎\n\n"
                "លោកអ្នកអាចសួរព័ត៌មានទាន់ហេតុការណ៍ តម្លៃហាងឆេង ឬលទ្ធផលបន្តផ្ទាល់បាន!\n\n"
                "👉 *របៀបប្រើប្រាស់៖*\n"
                "• `/search តម្លៃមាស និងប្រេងឥន្ធនៈថ្ងៃនេះនៅកម្ពុជា`\n"
                "• `/search លទ្ធផលបាល់ទាត់យប់មិញ`\n"
                "• `/search ព័ត៌មានជាតិថ្មីៗបំផុត`"
            )
            await query.edit_message_text(
                search_msg,
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 ត្រឡប់ទៅ AI Menu", callback_data="btn_ai_menu")]]),
                parse_mode="Markdown"
            )

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

        elif data in ["btn_upscale_2k", "btn_upscale_4k", "btn_upscale_8k", "btn_enhance_info", "btn_photo_enhance_help"]:
            if data == "btn_upscale_8k":
                target_mode = "8k"
            elif data == "btn_upscale_2k":
                target_mode = "2k"
            else: # btn_upscale_4k or btn_enhance_info or btn_photo_enhance_help
                target_mode = "4k"

            photos = query.message.photo if query.message else None
            if photos:
                mode_label = "8K Super-Res" if target_mode == "8k" else ("4K Ultra" if target_mode == "4k" else "2K HD")
                await query.answer(f"🔍 កំពុងធ្វើឱ្យរូបភាពកាន់តែច្បាស់ {mode_label}...")
                status_msg = await query.message.reply_text(f"🔍 *កំពុងដំណើរការ Super-Resolution កម្រិត {mode_label}...* ⏳", parse_mode="Markdown")
                await query.message.chat.send_action("upload_photo")
                try:
                    photo = photos[-1]
                    tg_file = await context.bot.get_file(photo.file_id)
                    img_bytes = bytes(await tg_file.download_as_bytearray())
                    from services.image_enhancer_service import enhance_image
                    enhanced_bytes, metrics = enhance_image(img_bytes, resolution_mode=target_mode)

                    import io
                    caption = (
                        f"✨ *រូបភាពត្រូវបានបង្កើនគុណភាព {metrics['mode']} រួចរាល់!* 🔍\n\n"
                        f"📐 *ទំហំដើម:* `{metrics['orig_width']} x {metrics['orig_height']}` px\n"
                        f"📈 *ទំហំថ្មី ({metrics['mode']}):* `{metrics['new_width']} x {metrics['new_height']}` px (+{metrics['scale']}x)\n"
                        f"⚡ *រយៈពេលដំណើរការ:* `{metrics['elapsed_seconds']}s`"
                    )

                    buttons = InlineKeyboardMarkup([
                        [
                            InlineKeyboardButton("💎 2K HD", callback_data="btn_upscale_2k"),
                            InlineKeyboardButton("🔥 4K Ultra", callback_data="btn_upscale_4k"),
                            InlineKeyboardButton("🌌 8K Super-Res", callback_data="btn_upscale_8k"),
                        ],
                        [
                            InlineKeyboardButton("💧 ដាក់ Watermark", callback_data="btn_watermark_info"),
                            InlineKeyboardButton("🔙 Menu ដើម", callback_data="btn_back_main")
                        ]
                    ])

                    photo_to_send = metrics.get("preview_bytes") or enhanced_bytes
                    await query.message.reply_photo(
                        photo=io.BytesIO(photo_to_send),
                        caption=caption,
                        reply_markup=buttons,
                        parse_mode="Markdown"
                    )

                    # If 4K or 8K, also send uncompressed Document so Telegram does not compress pixels
                    if target_mode in ["4k", "8k"]:
                        doc_io = io.BytesIO(enhanced_bytes)
                        doc_io.name = f"upscaled_{target_mode}_{metrics['new_width']}x{metrics['new_height']}.jpg"
                        await query.message.reply_document(
                            document=doc_io,
                            caption=f"📁 *ឯកសាររូបភាពដើម {metrics['mode']} មិនបង្រួម ({metrics['new_width']} x {metrics['new_height']} px)* ✨",
                            parse_mode="Markdown"
                        )

                    try:
                        await status_msg.delete()
                    except Exception:
                        pass
                except Exception as e_enh:
                    logger.error(f"Error enhancing image from button: {e_enh}")
                    await safe_edit_text(status_msg, f"❌ មិនអាចបង្កើនគុណភាពរូបភាពបានទេ៖ {str(e_enh)[:100]}")
            else:
                await query.answer()
                msg = (
                    "🔍 *របៀបធ្វើឱ្យរូបភាពកាន់តែច្បាស់ (AI Image Enhancer)៖*\n\n"
                    "👉 ចុច **Reply** លើរូបភាពណាមួយ រួចវាយ `/enhance` ឬ `/enhance 4k` ឬ `/enhance 8k`\n"
                    "👉 ឬផ្ញើរូបភាពថ្មីដោយដាក់ Caption ថា `/enhance 4k` ឬ `/enhance 8k`\n\n"
                    "Bot នឹងជួយសម្អាត Noise, Super-Resolution ពង្រីកដល់ 4K Ultra ឬ 8K Super-Res និងផ្ញើ File ដើមមិនបង្រួមជូនភ្លាមៗ! ✨"
                )
                await query.message.reply_text(msg, parse_mode="Markdown")

        elif data in ["btn_watermark_info", "btn_photo_watermark_help"]:
            photos = query.message.photo if query.message else None
            if photos:
                wm_text = user.first_name if user and user.first_name else "Smart Assistant"
                await query.answer(f"💧 កំពុងបោះត្រា '{wm_text}'...")
                status_msg = await query.message.reply_text(f"💧 *កំពុងបោះត្រា Watermark '{wm_text}' លើរូបភាព...* ⏳", parse_mode="Markdown")
                await query.message.chat.send_action("upload_photo")
                try:
                    photo = photos[-1]
                    tg_file = await context.bot.get_file(photo.file_id)
                    img_bytes = bytes(await tg_file.download_as_bytearray())
                    from services.watermark_service import apply_watermark
                    watermarked_bytes = apply_watermark(img_bytes, text=wm_text)

                    import io
                    caption = (
                        f"🛡️ *រូបភាពរបស់អ្នកត្រូវបានបោះត្រាការពារដោយជោគជ័យ!* ✨\n"
                        f"🏷️ _Watermark: {wm_text}_\n\n"
                        f"💡 _ប្រសិនបើចង់ប្ដូរឈ្មោះហាង ឬលេខទូរស័ព្ទផ្សេង សូមចុច Reply លើរូប រួចវាយ `/watermark <ឈ្មោះហាង>`_"
                    )
                    await query.message.reply_photo(
                        photo=io.BytesIO(watermarked_bytes),
                        caption=caption,
                        parse_mode="Markdown"
                    )
                    try:
                        await status_msg.delete()
                    except Exception:
                        pass
                except Exception as e_wm:
                    logger.error(f"Error watermarking image from button: {e_wm}")
                    await safe_edit_text(status_msg, f"❌ មិនអាចបោះត្រាលើរូបភាពបានទេ៖ {str(e_wm)[:100]}")
            else:
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

        elif data == "btn_pdf_help" or data == "btn_compress_help":
            await query.answer()
            msg = (
                "🗜️ *Universal File Master & PDF Converter* ✨\n\n"
                "👉 *របៀបប្រើប្រាស់ងាយៗ៖*\n"
                "1. **ផ្ញើ File PDF ចូលមកក្នុង Bot**\n"
                "2. Bot នឹងអាន & សង្ខេបខ្លឹមសារជាភាសាខ្មែរភ្លាមៗ\n"
                "3. បងអាចចុចប៊ូតុងខាងក្រោម File នោះដើម្បី៖\n"
                "   • `🔄 បម្លែងទៅ Word (.docx)` ➔ ទាញយកជា Word កែអត្ថបទបានភ្លាមៗ\n"
                "   • `🗜️ បង្រួមទំហំ (Compress)` ➔ បង្រួមទំហំ PDF ឱ្យតូចស្រាល\n"
                "   • `💬 Chat with PDF` ➔ សួរសំណួរលម្អិតពីឯកសារ\n\n"
                "💡 _អ្នកក៏អាចផ្ញើរូបភាពដើម្បីបង្រួមទំហំ KB/MB បានផងដែរ!_"
            )
            await query.edit_message_text(msg, reply_markup=get_back_keyboard(), parse_mode="Markdown")

        elif data == "btn_trip_menu":
            await query.answer()
            msg = (
                "🚗 *CamRoad Trip Planner & Car Hub (ជំនួយការធ្វើដំណើរ & ឡាន)* 🛣️\n\n"
                "👉 សូមជ្រើសរើសគោលដៅធ្វើដំណើរកម្សាន្តល្បីៗនៅកម្ពុជាខាងក្រោម "
                "ដើម្បីគណនាចម្ងាយផ្លូវ រយៈពេល ថ្លៃសាំងប៉ាន់ស្មាន និងកន្លែងឈប់សម្រាក៖\n\n"
                "💡 _ឬអ្នកអាចវាយបញ្ជាផ្ទាល់៖_ `/trip <ឈ្មោះខេត្ត ឬគោលដៅ>`\n"
                "ឧ. `/trip សៀមរាប` ឬ `/trip កំពត`"
            )
            await query.edit_message_text(msg, reply_markup=get_trip_menu_keyboard(), parse_mode="Markdown")

        elif data.startswith("btn_trip_dest_"):
            dest_key = data.replace("btn_trip_dest_", "")
            dest_data = CAMBODIA_ROUTES.get(dest_key)
            if dest_data:
                await query.answer("កំពុងគណនាការធ្វើដំណើរ...")
                trip = calculate_trip_details(dest_data, origin="រាជធានីភ្នំពេញ")
                report = format_trip_report(trip)
                kb = InlineKeyboardMarkup([
                    [InlineKeyboardButton("🗺️ បើកផែនទីនាំផ្លូវ (Google Maps)", url=trip["maps_dir_url"])],
                    [
                        InlineKeyboardButton("🚗 ជ្រើសរើសគោលដៅផ្សេង", callback_data="btn_trip_menu"),
                        InlineKeyboardButton("🔙 Menu ដើម", callback_data="btn_back_main")
                    ]
                ])
                await query.edit_message_text(report, reply_markup=kb, parse_mode="Markdown")

        elif data == "btn_car_diag_help":
            await query.answer()
            msg = (
                "🔧 *របៀបប្រើប្រាស់ Car Dashboard Diagnostic (វិភាគកុងទ័រឡាន)៖* 🚗\n\n"
                "1. **ថតរូបកុងទ័រឡាន** របស់អ្នកដែលមានលោតភ្លើង Warning (Check Engine, ABS, Oil, Battery, TPMS...)\n"
                "2. **ផ្ញើរូបភាពចូលមកក្នុង Bot នេះភ្លាមៗ**\n"
                "   • _(អាចដាក់ Caption `/car` ឬផ្ញើរូបធម្មតាក៏បាន)_\n"
                "3. AI នឹងវិភាគកម្រិតគ្រោះថ្នាក់ (🔴 ធ្ងន់ធ្ងរ / 🟡 មធ្យម) មូលហេតុ និងដំណោះស្រាយបន្ទាន់ជូនលោកអ្នក!\n\n"
                "💡 _ជួយឱ្យអ្នកដឹងពីបញ្ហាឡានភ្លាមៗ មុនពេលទៅដល់ហ្គារ៉ាស!_"
            )
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("🚗 គណនាការធ្វើដំណើរ (/trip)", callback_data="btn_trip_menu")],
                [InlineKeyboardButton("🔙 Menu ដើម", callback_data="btn_back_main")]
            ])
            await query.edit_message_text(msg, reply_markup=kb, parse_mode="Markdown")

        elif data == "btn_code_menu":
            await query.answer()
            msg = (
                "💻 *មជ្ឈមណ្ឌល Code Runner & Debugger ក្នុង Telegram* ⚡\n\n"
                "👉 *១. Run កូដ Python ផ្ទាល់ក្នុង Telegram៖*\n"
                "• វាយ `/run <កូដ Python>`\n"
                "• ឧទាហរណ៍៖\n"
                "```python\n/run print('Hello from Telegram Assistant!')\n```\n\n"
                "👉 *២. ជួសជុល និងពិនិត្យកូដ Error (AI Debugger)៖*\n"
                "• វាយ `/debug <កូដ Error>`\n"
                "• គាំទ្រគ្រប់ភាសា៖ Python, JS, PHP, HTML, CSS, SQL, C++, Java\n\n"
                "💡 _អ្នកអាចចុចតេស្តកូដគំរូខាងក្រោមភ្លាមៗ៖_"
            )
            await query.edit_message_text(msg, reply_markup=get_code_menu_keyboard(), parse_mode="Markdown")

        elif data == "btn_code_sample_1":
            await query.answer("⚡ កំពុងដំណើរការកូដ...")
            sample_code = (
                "students = [('សុខា', 88), ('ដារ៉ា', 94), ('វណ្ណា', 76)]\n"
                "for name, score in students:\n"
                "    grade = 'A' if score >= 90 else 'B' if score >= 80 else 'C'\n"
                "    print(f'សិស្ស: {name} | ពិន្ទុ: {score} | និទ្ទេស: {grade}')\n"
                "avg = sum(s[1] for s in students) / len(students)\n"
                "print(f'ពិន្ទុមធ្យមភាគរួម: {avg:.1f}')"
            )
            res = execute_python_code_sandboxed(sample_code)
            report = format_execution_result(res, sample_code)
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("▶️ Run Sample 2 (Loops)", callback_data="btn_code_sample_2")],
                [InlineKeyboardButton("🔙 ត្រឡប់ទៅ Code Hub", callback_data="btn_code_menu")]
            ])
            await query.edit_message_text(report, reply_markup=kb, parse_mode="Markdown")

        elif data == "btn_code_sample_2":
            await query.answer("⚡ កំពុងដំណើរការកូដ...")
            sample_code = (
                "def fibonacci(n):\n"
                "    res = [0, 1]\n"
                "    while len(res) < n:\n"
                "        res.append(res[-1] + res[-2])\n"
                "    return res\n\n"
                "fib = fibonacci(10)\n"
                "print('Fibonacci (10 numbers):', fib)\n"
                "evens = [x for x in fib if x % 2 == 0]\n"
                "print('Even numbers:', evens)"
            )
            res = execute_python_code_sandboxed(sample_code)
            report = format_execution_result(res, sample_code)
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("▶️ Run Sample 1 (Math)", callback_data="btn_code_sample_1")],
                [InlineKeyboardButton("🔙 ត្រឡប់ទៅ Code Hub", callback_data="btn_code_menu")]
            ])
            await query.edit_message_text(report, reply_markup=kb, parse_mode="Markdown")

        elif data == "btn_code_debug_help":
            await query.answer()
            msg = (
                "🐞 *របៀបប្រើប្រាស់ AI Code Debugger (ជួសជុលកូដ)៖*\n\n"
                "👉 វាយពាក្យបញ្ជា `/debug <កូដដែលមានបញ្ហា>`\n"
                "👉 ឧទាហរណ៍៖\n"
                "```python\n/debug\ndef add(a, b)\n    return a + b\nprint(add(5))\n```\n\n"
                "✨ AI នឹងប្រាប់មូលហេតុ និងផ្ដល់កូដដែលបានកែសម្រួលរួចជាស្រេចភ្លាមៗ!"
            )
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("💻 ត្រឡប់ទៅ Code Hub", callback_data="btn_code_menu")],
                [InlineKeyboardButton("🔙 Menu ដើម", callback_data="btn_back_main")]
            ])
            await query.edit_message_text(msg, reply_markup=kb, parse_mode="Markdown")

        elif data == "btn_briefing":
            await query.answer()
            first_name = user.first_name if user else "លោកអ្នក"
            status_text = "👑 *កំពុងរៀបចំរបាយការណ៍សង្ខេប VIP ជូនអ្នក...* ⏳"
            await query.edit_message_text(status_text, parse_mode="Markdown")
            from services.briefing_service import generate_executive_briefing
            briefing_text = await generate_executive_briefing(chat_id, user_name=first_name)
            await query.edit_message_text(
                briefing_text,
                reply_markup=get_briefing_keyboard(),
                parse_mode="Markdown",
                disable_web_page_preview=True
            )

        elif data == "btn_refresh_briefing":
            await query.answer("🔄 កំពុង Refresh របាយការណ៍...")
            first_name = user.first_name if user else "លោកអ្នក"
            from services.briefing_service import generate_executive_briefing
            briefing_text = await generate_executive_briefing(chat_id, user_name=first_name)
            await query.edit_message_text(
                briefing_text,
                reply_markup=get_briefing_keyboard(),
                parse_mode="Markdown",
                disable_web_page_preview=True
            )

        elif data == "btn_pdf_to_word":
            await query.answer("🔄 កំពុងបម្លែង PDF ទៅជា Word (.docx)...")
            file_id = context.user_data.get("last_pdf_file_id")
            filename = context.user_data.get("last_pdf_filename", "document.pdf")
            if not file_id:
                await query.answer("⚠️ រកមិនឃើញ file PDF ដើមឡើយ សូមផ្ញើ file ចូលម្តងទៀត!", show_alert=True)
                return
            try:
                tg_file = await context.bot.get_file(file_id)
                pdf_bytes = bytes(await tg_file.download_as_bytearray())
                from services.file_master_service import pdf_to_docx_bytes
                docx_bytes, stats = pdf_to_docx_bytes(pdf_bytes, filename)
                clean_name = filename.rsplit(".", 1)[0]
                caption = (
                    f"📄 *បានបម្លែងទៅជា Microsoft Word (.docx) ដោយជោគជ័យ!* ✨\n\n"
                    f"📑 ចំនួនទំព័រ៖ `{stats['pages']}` ទំព័រ\n"
                    f"📊 ទំហំ File Word៖ `{stats['docx_size_kb']} KB`\n"
                    f"💡 លោកអ្នកអាចបើកកែសម្រួលអត្ថបទក្នុង Word ឬ Google Docs បានភ្លាមៗ!"
                )
                import io
                await context.bot.send_document(
                    chat_id=chat_id,
                    document=io.BytesIO(docx_bytes),
                    filename=f"{clean_name}.docx",
                    caption=caption,
                    parse_mode="Markdown"
                )
            except Exception as e:
                logger.error(f"Error converting PDF to docx: {e}")
                await query.answer(f"❌ មិនអាចបម្លែងបានទេ៖ {e}", show_alert=True)

        elif data == "btn_compress_pdf":
            await query.answer("🗜️ កំពុងបង្រួមទំហំ File PDF...")
            file_id = context.user_data.get("last_pdf_file_id")
            filename = context.user_data.get("last_pdf_filename", "document.pdf")
            if not file_id:
                await query.answer("⚠️ រកមិនឃើញ file PDF ដើមឡើយ សូមផ្ញើ file ចូលម្តងទៀត!", show_alert=True)
                return
            try:
                tg_file = await context.bot.get_file(file_id)
                pdf_bytes = bytes(await tg_file.download_as_bytearray())
                from services.file_master_service import compress_pdf_bytes
                comp_bytes, stats = compress_pdf_bytes(pdf_bytes)
                clean_name = filename.rsplit(".", 1)[0]
                caption = (
                    f"🗜️ *បានបង្រួមទំហំ PDF ដោយជោគជ័យ!* ✨\n\n"
                    f"📐 ទំហំដើម៖ `{stats['original_kb']} KB`\n"
                    f"📉 ទំហំថ្មី៖ `{stats['compressed_kb']} KB`\n"
                    f"⚡ សន្សំសំចៃទំហំ៖ `-{stats['saved_pct']}%`\n"
                    f"📑 ចំនួនទំព័រ៖ `{stats['pages']}` ទំព័រ"
                )
                import io
                await context.bot.send_document(
                    chat_id=chat_id,
                    document=io.BytesIO(comp_bytes),
                    filename=f"compressed_{filename}",
                    caption=caption,
                    parse_mode="Markdown"
                )
            except Exception as e:
                logger.error(f"Error compressing PDF: {e}")
                await query.answer(f"❌ មិនអាចបង្រួមបានទេ៖ {e}", show_alert=True)

        elif data == "btn_back_main":
            await query.answer()
            first_name = user.first_name if user else "លោកអ្នក"
            msg = get_welcome_text(first_name, chat_id=chat_id, page=1)
            kb = get_main_menu_keyboard(chat_id, page=1)
            try:
                await query.edit_message_text(
                    msg,
                    reply_markup=kb,
                    parse_mode="Markdown"
                )
            except Exception:
                # If editing text fails (e.g. on a photo/media message), send fresh main menu
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=msg,
                    reply_markup=kb,
                    parse_mode="Markdown"
                )

        elif data == "btn_clean_chat":
            chat_id = query.message.chat_id if query.message else update.effective_chat.id
            current_msg_id = query.message.message_id if query.message else None
            await query.answer("🧹 កំពុងសម្អាតសារទាំងអស់ (ទាំងចាស់ និងថ្មី)...")

            from services.chat_cleaner_service import purge_chat_history, format_clean_notice_text
            
            # Delete the message containing the button first
            if query.message:
                try:
                    await query.message.delete()
                except Exception:
                    pass

            extra_ids = []
            if current_msg_id:
                extra_ids.append(current_msg_id)
            if context.user_data.get("last_menu_id"):
                extra_ids.append(context.user_data["last_menu_id"])
            if context.user_data.get("last_bot_msg_id"):
                extra_ids.append(context.user_data["last_bot_msg_id"])
            if context.user_data.get("last_remind_msg_id"):
                extra_ids.append(context.user_data["last_remind_msg_id"])

            # Purge all messages across chat history (both old and new)
            await purge_chat_history(
                bot=context.bot,
                chat_id=chat_id,
                current_msg_id=current_msg_id,
                sweep_depth=None,
                extra_ids=extra_ids
            )
                            
            context.user_data.pop("last_remind_msg_id", None)
            context.user_data.pop("last_menu_id", None)
            context.user_data.pop("last_bot_msg_id", None)

            clean_notice = format_clean_notice_text()
            sent_menu = await context.bot.send_message(
                chat_id=chat_id,
                text=clean_notice,
                reply_markup=get_main_menu_keyboard(chat_id),
                parse_mode="Markdown"
            )
            context.user_data["last_menu_id"] = sent_menu.message_id
            context.user_data["last_bot_msg_id"] = sent_menu.message_id
            try:
                from database import record_auto_clean_message
                record_auto_clean_message(chat_id, sent_menu.message_id)
            except Exception:
                pass

        elif data == "btn_delete_this_msg":
            try:
                await query.message.delete()
                await query.answer("🗑️ បានលុបសារនេះរួចរាល់")
            except Exception:
                await query.answer()

        elif data == "btn_crypto_menu":
            await query.answer("📈 កំពុងទាញយកតម្លៃ Crypto & TON...")
            from services.crypto_service import fetch_crypto_prices, format_crypto_overview_card
            from services.finance_service import fetch_exchange_rates, fetch_gold_price
            rates = await fetch_exchange_rates() or {}
            usd_khr = rates.get("KHR", 4085.0)
            gold = await fetch_gold_price()
            crypto_data = await fetch_crypto_prices()
            card_text = format_crypto_overview_card(crypto_data, usd_khr_rate=usd_khr, gold_info=gold)
            await query.edit_message_text(
                text=card_text,
                reply_markup=get_crypto_keyboard(),
                parse_mode="Markdown"
            )

        elif data == "btn_crypto_refresh":
            await query.answer("🔄 កំពុង Update តម្លៃចុងក្រោយ...")
            from services.crypto_service import fetch_crypto_prices, format_crypto_overview_card
            from services.finance_service import fetch_exchange_rates, fetch_gold_price
            rates = await fetch_exchange_rates() or {}
            usd_khr = rates.get("KHR", 4085.0)
            gold = await fetch_gold_price()
            crypto_data = await fetch_crypto_prices(force_refresh=True)
            card_text = format_crypto_overview_card(crypto_data, usd_khr_rate=usd_khr, gold_info=gold)
            await query.edit_message_text(
                text=card_text,
                reply_markup=get_crypto_keyboard(),
                parse_mode="Markdown"
            )

        elif data.startswith("btn_crypto_coin_"):
            sym = data.replace("btn_crypto_coin_", "").upper()
            await query.answer(f"📊 ព័ត៌មានកាក់ {sym}...")
            from services.crypto_service import fetch_crypto_prices, format_single_coin_card
            from services.finance_service import fetch_exchange_rates
            rates = await fetch_exchange_rates() or {}
            usd_khr = rates.get("KHR", 4085.0)
            crypto_data = await fetch_crypto_prices()
            coin = crypto_data.get(sym)
            if coin:
                coin_text = format_single_coin_card(coin, usd_khr_rate=usd_khr)
                kb = InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔔 កំណត់ Alert សម្រាប់កាក់នេះ", callback_data="btn_crypto_set_alert")],
                    [InlineKeyboardButton("📈 ត្រឡប់ទៅតារាង Crypto", callback_data="btn_crypto_menu")],
                    [InlineKeyboardButton("🔙 Menu ដើម", callback_data="btn_back_main")]
                ])
                await query.edit_message_text(text=coin_text, reply_markup=kb, parse_mode="Markdown")
            else:
                await query.answer(f"⚠️ មិនមានទិន្នន័យសម្រាប់ {sym}", show_alert=True)

        elif data == "btn_crypto_my_alerts":
            await query.answer("📋 បញ្ជី Price Alerts...")
            await alerts_list_command(update, context)

        elif data.startswith("btn_crypto_del_alert_"):
            aid_str = data.replace("btn_crypto_del_alert_", "")
            try:
                aid = int(aid_str)
                from database import delete_crypto_alert
                delete_crypto_alert(aid, chat_id)
                await query.answer("🗑️ បានលុប Alert នេះរួចរាល់!", show_alert=True)
            except Exception:
                await query.answer("❌ មិនអាចលុបបានទេ")
            await alerts_list_command(update, context)

        elif data == "btn_crypto_set_alert":
            await query.answer()
            tip = (
                "🔔 *[របៀបកំណត់ Alert តម្លៃកាក់]* 📈\n\n"
                "សូមវាយពាក្យបញ្ជាផ្ទាល់ក្នុងប្រអប់សារ៖\n"
                "`/alert <កាក់> <តម្លៃ>`\n\n"
                "• ឧទាហរណ៍៖ `/alert btc 85000`\n"
                "• ឧទាហរណ៍៖ `/alert ton 5.5`\n"
                "• ឧទាហរណ៍៖ `/alert eth 3200`\n"
                "• ឧទាហរណ៍៖ `/alert sol 120`\n\n"
                "Bot នឹងផ្ញើសារប្រាប់ភ្លាមៗនៅពេលទីផ្សារប្រែប្រួលដល់កម្រិតនោះ! 🚀"
            )
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("📈 ផ្សារ Crypto & TON", callback_data="btn_crypto_menu")],
                [InlineKeyboardButton("🔙 Menu ដើម", callback_data="btn_back_main")]
            ])
            await query.edit_message_text(text=tip, reply_markup=kb, parse_mode="Markdown")

        elif data == "btn_user_help":
            await query.answer()
            from services.user_resolver_service import validate_username_format
            _, _, tip = validate_username_format("")
            await query.edit_message_text(text=tip, reply_markup=get_back_keyboard(), parse_mode="Markdown")

        elif data.startswith("btn_content_view_"):
            view_mode = data.replace("btn_content_view_", "")
            await query.answer()
            last_content = context.user_data.get("last_content_data")
            if not last_content:
                from services.content_creator_service import generate_fallback_content
                last_content = generate_fallback_content("ផលិតផលគុណភាពខ្ពស់")
            from services.content_creator_service import format_content_card
            card_text = format_content_card(last_content, view_mode=view_mode)
            await query.edit_message_text(text=card_text, reply_markup=get_content_keyboard(view_mode), parse_mode="Markdown")

        elif data == "btn_content_regen":
            await query.answer("🔄 កំពុងបង្កើតមាតិកាថ្មី...")
            last_content = context.user_data.get("last_content_data", {})
            topic = last_content.get("topic", "ផលិតផលគុណភាពខ្ពស់")
            from services.content_creator_service import generate_social_content, format_content_card
            new_content = await generate_social_content(topic=topic, style="engaging")
            context.user_data["last_content_data"] = new_content
            card_text = format_content_card(new_content, view_mode="all")
            await query.edit_message_text(text=card_text, reply_markup=get_content_keyboard("all"), parse_mode="Markdown")

        elif data == "btn_content_help":
            await query.answer()
            tip = (
                "🎬 *[AI Content Creator Studio - ការណែនាំ]* ✨\n\n"
                "ជួយអ្នកលក់អនឡាញ & TikToker សរសេរ Caption លក់ដាច់, Script វីដេអូខ្លី ១៥ វិនាទី, និង Hashtags ល្បីៗស្វ័យប្រវត្តិ!\n\n"
                "💡 *របៀបប្រើប្រាស់៖*\n"
                "• វាយ៖ `/caption <ឈ្មោះទំនិញ ឬប្រធានបទ>`\n"
                "   (ឧ. `/caption កាហ្វេដូងក្រអូប`)\n"
                "   (ឧ. `/caption ឡេលាបស្បែក ស ភ្លឺថ្លា`)\n"
                "   (ឧ. `/caption អាវយឺតដៃខ្លី Oversize`)\n\n"
                "📸 *ឬគ្រាន់តែផ្ញើរូបថតផលិតផល* ដោយសរសេរភ្ជាប់ `/caption` ➔ AI នឹងស្កេនមើលផលិតផលក្នុងរូបភាព រួចរៀបចំ Caption និង Script វីដេអូជូនភ្លាមៗ! 🚀"
            )
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Menu ដើម", callback_data="btn_back_main")]
            ])
            await query.edit_message_text(text=tip, reply_markup=kb, parse_mode="Markdown")

        elif data == "btn_toggle_autoclean":
            from database import is_auto_clean_enabled, set_auto_clean_enabled
            current = is_auto_clean_enabled(chat_id)
            new_state = not current
            set_auto_clean_enabled(chat_id, new_state)
            status_alert = "✅ បានបើក Auto-Clean (១២:០០ ថ្ងៃ & ១២:០០ យប់)!" if new_state else "❌ បានបិទ Auto-Clean (១២:០០ ថ្ងៃ & ១២:០០ យប់)!"
            await query.answer(status_alert)
            first_name = user.first_name if user else "លោកអ្នក"
            await query.edit_message_text(
                get_welcome_text(first_name, chat_id=chat_id),
                reply_markup=get_main_menu_keyboard(chat_id),
                parse_mode="Markdown"
            )
            context.user_data["last_bot_msg_id"] = query.message.message_id
            context.user_data["last_menu_id"] = query.message.message_id

        elif data.startswith("menu_page_"):
            await query.answer()
            page_num = int(data.replace("menu_page_", ""))
            first_name = user.first_name if user else "លោកអ្នក"
            msg = get_welcome_text(first_name, chat_id=chat_id, page=page_num)
            kb = get_main_menu_keyboard(chat_id, page=page_num)
            try:
                await query.edit_message_text(msg, reply_markup=kb, parse_mode="Markdown")
            except Exception:
                pass

        elif data == "btn_choose_persona":
            await query.answer()
            msg = (
                "🎭 *ជ្រើសរើស Persona / Role សម្រាប់គណនីរបស់អ្នក* ✨\n\n"
                "ជ្រើសរើសប្រភេទការងាររបស់អ្នកដើម្បីឱ្យ Bot បង្ហាញប៊ូតុងមុខងារដែលត្រូវនឹងតម្រូវការបំផុត៖\n\n"
                "🎓 *១. របៀបសិស្ស/និស្សិត (Student Mode):*\n"
                "• ដោះស្រាយលំហាត់ AI, Chat with PDF, បកប្រែភាសា Pro, ពិនិត្យអក្ខរាវិរុទ្ធ, សង្ខេប YouTube\n\n"
                "💼 *២. របៀបអាជីវកម្ម/លក់ដូរ (Business Mode):*\n"
                "• ស្កេនវិក្កយបត្រ AI, ចំណូល-ចំណាយ Budget, ក្រាហ្វិក Donut Chart, Watermark ទំនិញ, KHQR, តម្លៃមាស/សាំង\n\n"
                "🎬 *៣. របៀបអ្នកកាត់ត & Media (Creator Mode):*\n"
                "• ទាញយក 4K/8K, YouTube Playlist, កាត់វីដេអូ /trim, GIF Maker, បង្កើតរូប AI /imagine, Subtitle ខ្មែរ\n\n"
                "🌐 *៤. បង្ហាញទាំងអស់ (All-in-One Slider):*\n"
                "• ប្រើប្រាស់ Paginated Slider Menu ៣ ទំព័រ [1/3] ដូចធម្មតា\n\n"
                "👇 _សូមចុចជ្រើសរើសខាងក្រោម៖_"
            )
            kb = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("🎓 របៀបសិស្ស/និស្សិត", callback_data="set_persona_student"),
                    InlineKeyboardButton("💼 របៀបអាជីវកម្ម/លក់ដូរ", callback_data="set_persona_business"),
                ],
                [
                    InlineKeyboardButton("🎬 របៀបអ្នកកាត់ត & Media", callback_data="set_persona_creator"),
                    InlineKeyboardButton("🌐 បង្ហាញទាំងអស់ (Slider)", callback_data="set_persona_all"),
                ],
                [
                    InlineKeyboardButton("🔙 Menu ដើម", callback_data="btn_back_main")
                ]
            ])
            await query.edit_message_text(msg, reply_markup=kb, parse_mode="Markdown")

        elif data.startswith("set_persona_"):
            target_persona = data.replace("set_persona_", "")
            set_user_persona(chat_id, target_persona)
            persona_names = {
                "student": "🎓 របៀបសិស្ស/និស្សិត (Student Mode)",
                "business": "💼 របៀបអាជីវកម្ម/លក់ដូរ (Business Mode)",
                "creator": "🎬 របៀបអ្នកកាត់ត & Media (Creator Mode)",
                "all": "🌐 បង្ហាញទាំងអស់ (All-in-One Slider)"
            }
            chosen_name = persona_names.get(target_persona, "Menu")
            await query.answer(f"✅ បានប្តូរទៅកាន់ {chosen_name} រួចរាល់!", show_alert=False)
            first_name = user.first_name if user else "លោកអ្នក"
            msg = get_welcome_text(first_name, chat_id=chat_id, page=1)
            kb = get_main_menu_keyboard(chat_id, page=1)
            try:
                await query.edit_message_text(msg, reply_markup=kb, parse_mode="Markdown")
            except Exception:
                await context.bot.send_message(chat_id=chat_id, text=msg, reply_markup=kb, parse_mode="Markdown")

        elif data == "noop":
            await query.answer()

        elif data == "btn_imagine_help":
            await query.answer()
            tip = (
                "🎨 *[AI Image Generator - បង្កើតរូបភាព AI]* ✨\n\n"
                "បង្កើតរូបភាព Ultra HD ពីពាក្យពិពណ៌នារបស់អ្នកដោយឥតគិតថ្លៃ!\n\n"
                "👉 *របៀបប្រើប្រាស់៖*\n"
                "វាយ៖ `/imagine <ពិពណ៌នារូបភាពដែលអ្នកចង់បាន>`\n\n"
                "• ឧទាហរណ៍៖ `/imagine រថយន្តទំនើបបើកកាត់ប្រាសាទអង្គរវត្តពេលថ្ងៃលិច`\n"
                "• ឧទាហរណ៍៖ `/imagine cute anime girl reading book in cozy coffee shop 4k cinematic`\n"
                "• ឧទាហរណ៍៖ `/imagine នាគរាជខ្មែរហោះលើផ្ទៃមេឃពណ៌មាស`\n\n"
                "⚡ *លក្ខណៈពិសេស៖* ក្រោយពេល Render រួច អ្នកអាចចុច Upscale 2K, 4K, ឬ 8K Super-Resolution បានភ្លាមៗ!"
            )
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Menu ដើម", callback_data="btn_back_main")]
            ])
            await query.edit_message_text(text=tip, reply_markup=kb, parse_mode="Markdown")

        elif data == "btn_summarize_help":
            await query.answer()
            tip = (
                "📝 *[YouTube AI Video Summarizer - សង្ខេបវីដេអូ]* ✨\n\n"
                "ជួយសន្សំពេលវេលាដោយមិនបាច់មើលវីដេអូរាប់ម៉ោង! AI នឹងស្ដាប់ និងសង្ខេបចំណុចសំខាន់ៗជាភាសាខ្មែរជូនភ្លាមៗ!\n\n"
                "👉 *របៀបប្រើប្រាស់៖*\n"
                "វាយ៖ `/summarize <Link វីដេអូ YouTube>`\n\n"
                "• ឧទាហរណ៍៖ `/summarize https://www.youtube.com/watch?v=...`\n"
                "💡 _ឬគ្រាន់តែ Reply លើសារដែលមាន Link វីដេអូ ដោយវាយពាក្យ:_ `/summarize` ឬ `/sum`"
            )
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Menu ដើម", callback_data="btn_back_main")]
            ])
            await query.edit_message_text(text=tip, reply_markup=kb, parse_mode="Markdown")

        elif data == "btn_trim_help":
            await query.answer()
            tip = (
                "✂️ *[ឧបករណ៍កាត់តវីដេអូក្នុង Chat (Video Trimmer)]* 🎬\n\n"
                "កាត់យកតែវិនាទី ឬនាទីដែលចង់បានដោយមិនចាំបាច់ប្រើកម្មវិធីកាត់តស្មុគស្មាញ!\n\n"
                "👉 *របៀបប្រើប្រាស់៖*\n"
                "1️⃣ ផ្ញើវីដេអូ ឬ Copy Link វីដេអូ YouTube/TikTok ចូល Bot\n"
                "2️⃣ Reply លើវីដេអូនោះដោយវាយ៖ `/trim <វិនាទីចាប់ផ្តើម> <វិនាទីបញ្ចប់>`\n\n"
                "• ឧទាហរណ៍៖ `/trim 00:10 00:45` (កាត់ពីវិនាទីទី ១០ ដល់ ៤៥)\n"
                "• ឧទាហរណ៍៖ `/trim 01:20 02:00` (កាត់រយៈពេល ៤០ វិនាទី)\n\n"
                "⚡ Bot នឹងកាត់ និង Render វីដេអូថ្មីផ្ញើជូនភ្លាមៗ!"
            )
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Menu ដើម", callback_data="btn_back_main")]
            ])
            await query.edit_message_text(text=tip, reply_markup=kb, parse_mode="Markdown")

        elif data == "btn_gif_help":
            await query.answer()
            tip = (
                "🎞️ *[បម្លែងវីដេអូខ្លីជា Sticker / Animated GIF]* ✨\n\n"
                "បង្កើត Animated GIF ទុកផ្ញើលេងក្នុង Group ឬឆាតផ្ទាល់ខ្លួន!\n\n"
                "👉 *របៀបប្រើប្រាស់៖*\n"
                "• Reply លើវីដេអូខ្លី ឬ TikTok Video ដោយវាយពាក្យ៖ `/gif`\n"
                "• ឬវាយ៖ `/gif 00:05 00:10` ដើម្បីកាត់យក ៥ វិនាទីធ្វើជា GIF រលូនស្អាត!\n\n"
                "🚀 Bot នឹងបម្លែង និងផ្ញើចេញជា GIF Animation ភ្លាមៗ!"
            )
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Menu ដើម", callback_data="btn_back_main")]
            ])
            await query.edit_message_text(text=tip, reply_markup=kb, parse_mode="Markdown")

        elif data == "btn_subtitle_help":
            await query.answer()
            tip = (
                "📑 *[ទាញយក Subtitle / ចំណងជើងរងជាភាសាខ្មែរ]* 🇰🇭\n\n"
                "ទាញយក Subtitle ពី YouTube និងប្រើប្រាស់ AI បកប្រែជាភាសាខ្មែរស្វ័យប្រវត្តិ!\n\n"
                "👉 *របៀបប្រើប្រាស់៖*\n"
                "• វាយ៖ `/subtitle <Link YouTube>`\n"
                "• ឬចុចប៊ូតុង *📑 Subtitle* នៅពេលទាញយកវីដេអូ YouTube\n\n"
                "📂 Bot នឹងផ្ញើចេញជា File `.srt` ដែលអាចចាក់ជាមួយ VLC Player ឬ Player ផ្សេងៗបានយ៉ាងងាយស្រួល!"
            )
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Menu ដើម", callback_data="btn_back_main")]
            ])
            await query.edit_message_text(text=tip, reply_markup=kb, parse_mode="Markdown")

        elif data == "btn_playlist_help":
            await query.answer()
            tip = (
                "🎧 *[ទាញយកទាំង Playlist YouTube / TikTok Profile]* 🚀\n\n"
                "ទាញយកចម្រៀង MP3 ឬវីដេអូទាំងអស់ក្នុង Playlist តែម្តងដោយស្វ័យប្រវត្តិ!\n\n"
                "👉 *របៀបប្រើប្រាស់៖*\n"
                "• វាយ៖ `/playlist <Link YouTube Playlist>`\n"
                "• ឧទាហរណ៍៖ `/playlist https://www.youtube.com/playlist?list=...`\n\n"
                "📻 បទចម្រៀងទាំងអស់ក្នុង Playlist នឹងត្រូវទាញយក និងបញ្ជូនចូល Channel @Song182 ទាំងអស់ក្នុងពេលតែមួយ!"
            )
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Menu ដើម", callback_data="btn_back_main")]
            ])
            await query.edit_message_text(text=tip, reply_markup=kb, parse_mode="Markdown")

        elif data == "btn_botserver_info":
            await query.answer()
            tip = (
                "🖥️ *[Local Bot API Server (ផ្ញើ File បានដល់ 2,000 MB / 2 GB)]* 🚀\n\n"
                "• *ដែនកំណត់ Telegram ធម្មតា:* ត្រឹមតែ 50 MB ប៉ុណ្ណោះ\n"
                "• *ជាមួយ Local Bot API Server:* អនុញ្ញាតឱ្យ Bot អាចផ្ញើឯកសារវីដេអូ 4K/8K ធំៗបានដល់ *2,000 MB (2 GB)* ពេញទំហំដោយផ្ទាល់ក្នុង Chat!\n\n"
                "💡 ប្រព័ន្ធត្រូវបានរៀបចំរួចរាល់សម្រាប់ Local API Routing ជួយឱ្យការទាញយក 4K/8K ដំណើរការបានរហ័ស និងមិនជាប់កំណត់ 50MB ឡើយ!"
            )
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Menu ដើម", callback_data="btn_back_main")]
            ])
            await query.edit_message_text(text=tip, reply_markup=kb, parse_mode="Markdown")

        elif data == "btn_speak_help":
            await query.answer()
            tip = (
                "🗣️ *[Text-to-Speech (TTS) - អានជាសំឡេងខ្មែរ/អង់គ្លេស]* 🎙️\n\n"
                "បម្លែងអត្ថបទទៅជាសំឡេងនិយាយយ៉ាងពិរោះ និងរលូន!\n\n"
                "👉 *របៀបប្រើប្រាស់៖*\n"
                "• វាយ៖ `/speak <អត្ថបទដែលចង់ឱ្យអាន>`\n"
                "• ឧទាហរណ៍៖ `/speak សួស្តីបងប្អូនទាំងអស់គ្នា សូមស្វាគមន៍មកកាន់ថ្ងៃថ្មី!`\n"
                "• ឧទាហរណ៍៖ `/speak Good morning everyone, have a wonderful day!`\n\n"
                "💡 _ឬគ្រាន់តែ Reply លើសារណាមួយដោយវាយពាក្យ:_ `/speak`"
            )
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Menu ដើម", callback_data="btn_back_main")]
            ])
            await query.edit_message_text(text=tip, reply_markup=kb, parse_mode="Markdown")

        elif data == "btn_translate_help":
            await query.answer()
            tip = (
                "🌐 *[បកប្រែភាសា Pro (Khmer ⬄ English)]* 📚\n\n"
                "បកប្រែពាក្យ ឃ្លា និងអត្ថបទវែងៗយ៉ាងត្រឹមត្រូវតាមក្បួនវេយ្យាករណ៍!\n\n"
                "👉 *របៀបប្រើប្រាស់៖*\n"
                "• វាយ៖ `/translate <ពាក្យ ឬអត្ថបទ>`\n"
                "• ឧទាហរណ៍៖ `/translate Artificial intelligence transforms the future`\n"
                "• ឧទាហរណ៍៖ `/translate កម្ពុជាមានសម្បត្តិវប្បធម៌ដ៏សម្បូរបែប`\n\n"
                "💡 _ឬគ្រាន់តែ Reply លើសារណាមួយដោយវាយពាក្យ:_ `/translate`"
            )
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Menu ដើម", callback_data="btn_back_main")]
            ])
            await query.edit_message_text(text=tip, reply_markup=kb, parse_mode="Markdown")

        elif data == "btn_check_help":
            await query.answer()
            tip = (
                "✍️ *[ពិនិត្យអក្ខរាវិរុទ្ធភាសាខ្មែរ (Chuon Nath Dictionary)]* 📖\n\n"
                "កែតម្រូវពាក្យខុស និងអក្ខរាវិរុទ្ធតាមក្បួនខ្នាតវចនានុក្រម សម្តេចព្រះសង្ឃរាជ ជួន ណាត!\n\n"
                "👉 *របៀបប្រើប្រាស់៖*\n"
                "• វាយ៖ `/check <អត្ថបទរបស់អ្នក>`\n"
                "• ឧទាហរណ៍៖ `/check ខ្ញុំកំពុងសរេសរលិខិត`\n\n"
                "💡 _Bot នឹងបង្ហាញពាក្យខុស ពាក្យត្រូវ និងអត្ថន័យច្បាស់លាស់!_"
            )
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Menu ដើម", callback_data="btn_back_main")]
            ])
            await query.edit_message_text(text=tip, reply_markup=kb, parse_mode="Markdown")

        elif data == "btn_ai_vision_help":
            await query.answer()
            tip = (
                "📚 *[AI Vision - ដោះស្រាយលំហាត់ & ស្កេនរូបភាព]* 🧠\n\n"
                "ជួយសិស្ស និស្សិតដោះស្រាយលំហាត់គណិត រូបវិទ្យា គីមី និងស្កេនសំណួរផ្សេងៗ!\n\n"
                "👉 *របៀបប្រើប្រាស់៖*\n"
                "1️⃣ ថតរូប ឬផ្ញើរូបភាពលំហាត់/សំណួរចូលក្នុង Bot\n"
                "2️⃣ សរសេរ Caption ឬ Reply ដោយសរសេរពាក្យបញ្ជា (ឧ. `ជួយដោះស្រាយលំហាត់នេះមួយ` ឬ `ពន្យល់រូបមន្តនេះ`)\n\n"
                "🚀 Gemini AI Vision នឹងវិភាគរូបភាព និងពន្យល់ដំណោះស្រាយជាជំហានៗយ៉ាងក្បោះក្បាយ!"
            )
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Menu ដើម", callback_data="btn_back_main")]
            ])
            await query.edit_message_text(text=tip, reply_markup=kb, parse_mode="Markdown")

        elif data == "btn_photo_to_docx":
            img_bytes = context.user_data.get("last_photo_bytes")
            if not img_bytes:
                await query.answer("⚠️ សូមផ្ញើរូបភាព ឬថតរូបឯកសារចូល Bot ជាមុនសិនណា៎!", show_alert=True)
            else:
                await query.answer("📝 កំពុងបម្លែងជា Word (.docx)...")
                await context.bot.send_chat_action(chat_id=chat_id, action="upload_document")
                from services.doc_converter_service import convert_image_to_docx
                import io
                docx_bytes, filename, summary = await convert_image_to_docx(img_bytes)
                if docx_bytes:
                    await context.bot.send_document(
                        chat_id=chat_id,
                        document=io.BytesIO(docx_bytes),
                        filename=filename,
                        caption=f"📝 *បានបម្លែងជា Word (.docx) ជោគជ័យ!* ✨\n\n_{summary}_\n\n🤖 Smart Assistant Bot 🚀",
                        parse_mode="Markdown"
                    )
                else:
                    await context.bot.send_message(chat_id=chat_id, text="❌ មិនអាចបម្លែងជា Word បានទេ។ សូមសាកល្បងជាមួយរូបភាពច្បាស់ជាងនេះ។")

        elif data == "btn_photo_to_xlsx":
            img_bytes = context.user_data.get("last_photo_bytes")
            if not img_bytes:
                await query.answer("⚠️ សូមផ្ញើរូបភាពតារាង ឬវិក្កយបត្រចូល Bot ជាមុនសិនណា៎!", show_alert=True)
            else:
                await query.answer("📊 កំពុងបម្លែងជា Excel (.xlsx)...")
                await context.bot.send_chat_action(chat_id=chat_id, action="upload_document")
                from services.doc_converter_service import convert_image_to_xlsx
                import io
                xlsx_bytes, filename, summary = await convert_image_to_xlsx(img_bytes)
                if xlsx_bytes:
                    await context.bot.send_document(
                        chat_id=chat_id,
                        document=io.BytesIO(xlsx_bytes),
                        filename=filename,
                        caption=f"📊 *បានបម្លែងជា Excel (.xlsx) ជោគជ័យ!* ✨\n\n_{summary}_\n\n🤖 Smart Assistant Bot 🚀",
                        parse_mode="Markdown"
                    )
                else:
                    await context.bot.send_message(chat_id=chat_id, text="❌ មិនអាចបម្លែងជា Excel បានទេ។ សូមសាកល្បងជាមួយរូបភាពច្បាស់ជាងនេះ។")

        elif data == "btn_event_help":
            await query.answer()
            tip = (
                "📅 *[Google Calendar Auto-Sync - ការណែនាំ]* ✨\n\n"
                "គ្រាន់តែប្រាប់ Bot ពីការណាត់ជួបជាភាសាខ្មែរធម្មតា ➔ AI នឹងរៀបចំ Event ចូល Google Calendar និងដាស់តឿនមុន ៦០ នាទីដោយស្វ័យប្រវត្តិ!\n\n"
                "👉 *របៀបប្រើប្រាស់៖*\n"
                "វាយ៖ `/event <ព័ត៌មានណាត់ជួប>` ឬ `/schedule <ព័ត៌មាន>`\n\n"
                "• ឧទាហរណ៍៖ `/event ស្អែកម៉ោង ២ រសៀល ណាត់ជួបអតិថិជននៅ Brown Bokor`\n"
                "• ឧទាហរណ៍៖ `/event ថ្ងៃចន្ទសប្តាហ៍ក្រោយ ម៉ោង 9:00 ព្រឹក ប្រជុំគម្រោងក្រុមហ៊ុន`\n"
                "• ឧទាហរណ៍៖ `/event ថ្ងៃទី 28 ខែវិច្ឆិកា ម៉ោង 7 យប់ ញ៉ាំបាយជុំគ្នា`\n\n"
                "⚡ *លក្ខណៈពិសេស៖* មានប៊ូតុងចុច ១ ដងចូល Google Calendar ផ្ទាល់ និងផ្ញើឯកសារ .ICS សម្រាប់ iPhone/Android!"
            )
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu ដើម", callback_data="btn_back_main")]])
            await query.edit_message_text(text=tip, reply_markup=kb, parse_mode="Markdown")

        elif data == "btn_word_help":
            await query.answer()
            tip = (
                "📝 *[រូបថតឯកសារ ➔ Microsoft Word (.docx)]* ✨\n\n"
                "បម្លែងរូបថតក្រដាសឯកសារ សៀវភៅ ឬអត្ថបទឱ្យក្លាយជា File Word ដែលអាច Edit បាន មិនបាច់អង្គុយវាយឡើងវិញ!\n\n"
                "👉 *របៀបប្រើប្រាស់៖*\n"
                "1️⃣ ថតរូប ឬផ្ញើរូបភាពឯកសារចូល Bot\n"
                "2️⃣ ភ្ជាប់ Caption ឬ Reply លើរូបនោះដោយវាយ៖ `/word` ឬ `/docx`\n"
                "   (ឬចុចប៊ូតុង *📝 បម្លែង Word* ក្រោមរូបភាព)\n\n"
                "📂 Bot នឹងផ្ញើចេញជា File `.docx` ស្អាតកម្រិត Professional ភ្លាមៗ!"
            )
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu ដើម", callback_data="btn_back_main")]])
            await query.edit_message_text(text=tip, reply_markup=kb, parse_mode="Markdown")

        elif data == "btn_excel_help":
            await query.answer()
            tip = (
                "📊 *[រូបថតតារាង / វិក្កយបត្រ ➔ Microsoft Excel (.xlsx)]* ✨\n\n"
                "ស្កេនទាញយកតារាងលេខ វិក្កយបត្រ ឬតារាងទំនិញពីរូបថត បម្លែងទៅជា File Excel មានជួរឈរនិងជួរដេកត្រឹមត្រូវ!\n\n"
                "👉 *របៀបប្រើប្រាស់៖*\n"
                "1️⃣ ផ្ញើរូបថតតារាង ឬវិក្កយបត្រចូល Bot\n"
                "2️⃣ ភ្ជាប់ Caption ឬ Reply លើរូបនោះដោយវាយ៖ `/sheet`\n"
                "   (ឬចុចប៊ូតុង *📊 បម្លែង Excel* ក្រោមរូបភាព)\n\n"
                "📂 Bot នឹងផ្ញើចេញជា File `.xlsx` ដែលអាចបើកក្នុង Excel ឬ Google Sheets បានភ្លាមៗ!"
            )
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu ដើម", callback_data="btn_back_main")]])
            await query.edit_message_text(text=tip, reply_markup=kb, parse_mode="Markdown")

        elif data == "btn_shorts_help":
            await query.answer()
            tip = (
                "✂️ *[Viral Shorts Auto-Clipper - កាត់វីដេអូខ្លី]* 🎬\n\n"
                "ដាក់ Link វីដេអូ YouTube វែង ➔ AI ស្វែងរកវិនាទីដែលជក់ចិត្តបំផុត រួចកាត់ជាវីដេអូខ្លី ៣០ ទៅ ៦០ វិនាទីសម្រាប់ TikTok/Reels!\n\n"
                "👉 *របៀបប្រើប្រាស់៖*\n"
                "វាយ៖ `/shorts <Link YouTube>` ឬ `/clip <Link YouTube>`\n\n"
                "• ឧទាហរណ៍៖ `/shorts https://www.youtube.com/watch?v=...`\n"
                "💡 _ឬគ្រាន់តែ Reply លើសារដែលមាន Link វីដេអូ ដោយវាយ:_ `/shorts`"
            )
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu ដើម", callback_data="btn_back_main")]])
            await query.edit_message_text(text=tip, reply_markup=kb, parse_mode="Markdown")

        elif data == "btn_web_builder":
            await query.answer()
            tip = (
                "🌐 *[Instant Mini Landing Page Builder - បង្កើត Web ផ្ទាល់ខ្លួន 30s]* ✨\n\n"
                "គ្រាន់តែប្រាប់ Bot ពីអាជីវកម្ម ឬជំនាញរបស់អ្នក ➔ AI នឹងរចនាគេហទំព័រ Landing Page ដ៏ទំនើបមួយភ្លាមៗ "
                "ដែលបើកមើលបានលើ Telegram Mini App ព្រមទាំងទាញយក File កូដ HTML ទៅ Host លើ Domain ផ្ទាល់ខ្លួនបាន!\n\n"
                "👉 *របៀបប្រើប្រាស់៖*\n"
                "វាយ៖ `/web <ព័ត៌មានដែលចង់បាន>` ឬ `/page <ព័ត៌មាន>`\n\n"
                "• ឧទាហរណ៍៖ `/web ខ្ញុំជាអ្នកថតរូបឈ្មោះ សុខា ចង់បានគេហទំព័រដាក់រូបថត សេវាកម្ម និងលេខទូរស័ព្ទ 012888999 @sokha_photo`\n"
                "• ឧទាហរណ៍៖ `/web ហាងកាហ្វេ Cafe Amazon សាខាទួលគោក មានម៉ឺនុយភេសជ្ជៈ ប្រូម៉ូសិន និងផែនទី`\n"
                "• ឧទាហរណ៍៖ `/web អ្នកលក់ឡេ Online សេវាដឹក ២៥ ខេត្តក្រុង មានប៊ូតុងឆាត Telegram និង Facebook`\n"
                "• ឧទាហរណ៍៖ `/web Portfolio អ្នកសរសេរកូដ Full-Stack Developer ជំនាញ Python & React`\n\n"
                "👇 *ឬចុចជ្រើសរើសគំរូរហ័ស (Quick Presets) ខាងក្រោមដើម្បីសាកល្បង៖*"
            )
            kb = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("📸 គំរូអ្នកថតរូប", callback_data="web_preset_photo"),
                    InlineKeyboardButton("☕ គំរូហាងកាហ្វេ", callback_data="web_preset_cafe"),
                ],
                [
                    InlineKeyboardButton("💄 គំរូលក់ទំនិញ", callback_data="web_preset_shop"),
                    InlineKeyboardButton("💻 គំរូ Portfolio IT", callback_data="web_preset_dev"),
                ],
                [InlineKeyboardButton("🔙 Menu ដើម", callback_data="btn_back_main")]
            ])
            await query.edit_message_text(text=tip, reply_markup=kb, parse_mode="Markdown")

        elif data.startswith("web_preset_"):
            preset_type = data.replace("web_preset_", "")
            preset_prompts = {
                "photo": "ខ្ញុំជាអ្នកថតរូប និងវីដេអូអាជីព (Sokha Media Studio) សេវាកម្មថតរូបមង្គលការ Event និង Studio ទំនាក់ទំនង 012 888 999 @sokha_media",
                "cafe": "ហាងកាហ្វេ Cafe Arom & Bakery បរិយាកាសស្ងប់ស្ងាត់ មានភេសជ្ជៈឆ្ងាញ់ៗ កាហ្វេទឹកដោះគោ និងនំខេក ទំនាក់ទំនង 016 777 888 @cafearom",
                "shop": "ហាងលក់គ្រឿងសម្អាង និងម៉ូដសម្លៀកបំពាក់នារីទាន់សម័យ (Beauty & Fashion Shop) សេវាដឹក ២៥ ខេត្តក្រុង ទំនាក់ទំនង 098 555 666 @beautyshop",
                "dev": "Professional Full-Stack Developer & AI Specialist (Python, React, Cloud) ទទួលធ្វើ Website, Mobile App & Telegram Bot ទំនាក់ទំនង 092 333 444 @dev_expert"
            }
            preset_prompt = preset_prompts.get(preset_type, "សេវាកម្មអាជីវកម្ម និងពាណិជ្ជកម្មកម្ពុជា")
            await query.answer("កំពុងរចនាគេហទំព័រ...")
            await query.edit_message_text("🌐 *AI កំពុងរចនា និងបង្កើតគេហទំព័រ Landing Page ដ៏ទំនើបរបស់អ្នក...* ⏳\nសូមរង់ចាំប្រហែល ៥ វិនាទី! 🚀", parse_mode="Markdown")

            from services.web_builder_service import generate_landing_page
            import io
            ok, site_id, site_url, html_str, summary = await generate_landing_page(preset_prompt, chat_id)
            if ok:
                buttons = [
                    [InlineKeyboardButton("🌐 បើកមើល Website លើទូរស័ព្ទ (Mini App)", web_app=WebAppInfo(url=site_url))],
                    [InlineKeyboardButton("🔗 បើកមើលលើ Browser / Safari", url=site_url)],
                    [InlineKeyboardButton("🔙 Menu ដើម", callback_data="btn_back_main")]
                ]
                card_text = (
                    "🎉 *[បានបង្កើតគេហទំព័រ Landing Page ជោគជ័យ!]* 🌐✨\n\n"
                    f"{summary}\n\n"
                    "💡 *លក្ខណៈពិសេស៖*\n"
                    "• រចនាបថ Glassmorphism Dark Mode ទំនើបកម្រិតអន្តរជាតិ\n"
                    "• បង្ហាញរូបភាពច្បាស់ HD និងសេវាកម្មច្បាស់ៗ\n"
                    "• ប៊ូតុង Call ភ្លាមៗ និង Chat Telegram ផ្ទាល់\n"
                    "• ដំណើរការរលូនលើទូរស័ព្ទដៃ iPhone និង Android\n\n"
                    "👇 _ចុចប៊ូតុងខាងក្រោមដើម្បីបើកមើលភ្លាមៗ ឬទាញយកឯកសារកូដ HTML ខាងក្រោម៖_"
                )
                await query.edit_message_text(text=card_text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="Markdown")

                html_file = io.BytesIO(html_str.encode("utf-8"))
                html_file.name = f"{site_id}.html"
                await query.message.reply_document(
                    document=html_file,
                    filename=f"{site_id}.html",
                    caption=f"📎 *ឯកសារកូដ Website ពេញលេញ (.html)*\n_លោកអ្នកអាចទាញយក File នេះយកទៅ Host លើ Domain ផ្ទាល់ខ្លួន (Netlify, Vercel, GitHub) បានយ៉ាងងាយស្រួល!_",
                    parse_mode="Markdown"
                )
            else:
                await query.edit_message_text(f"❌ {summary}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu ដើម", callback_data="btn_back_main")]]))

        elif data == "btn_scam_help":
            await query.answer()
            tip = (
                "🔍 *[Phishing & Scam Link Scanner - ស្កេន Link បោក]* 🛡️\n\n"
                "ត្រួតពិនិត្យសុវត្ថិភាពតំណភ្ជាប់ (Link) គេហទំព័របោកប្រាស់ លួចគណនី Telegram ឬមេរោគ APK ធនាគារក្លែងក្លាយ!\n\n"
                "👉 *របៀបប្រើប្រាស់៖*\n"
                "• វាយ៖ `/scan <Link ឬអត្ថបទសារ>`\n"
                "• ឧទាហរណ៍៖ `/scan https://aba-fake-login.com`\n"
                "💡 _ឬគ្រាន់តែ Forward សារគួរឱ្យសង្ស័យចូលក្នុង Bot នេះ!_"
            )
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu ដើម", callback_data="btn_back_main")]])
            await query.edit_message_text(text=tip, reply_markup=kb, parse_mode="Markdown")

        elif data == "btn_tempmail" or data == "mail_refresh":
            await query.answer("កំពុងពិនិត្យសារ...")
            from services.temp_mail_service import check_inbox, get_current_email, generate_temp_email
            email = get_current_email(chat_id)
            if not email:
                email = await generate_temp_email(chat_id)

            success, curr_email, messages = await check_inbox(chat_id)
            
            kb_rows = [
                [
                    InlineKeyboardButton("🔄 ពិនិត្យសារថ្មី (Check Inbox)", callback_data="mail_refresh"),
                    InlineKeyboardButton("🆕 បង្កើត Email ថ្មី", callback_data="mail_new"),
                ]
            ]

            if messages:
                mail_list_text = "📬 *សារដែលបានទទួលក្នុង Inbox៖*\n\n"
                for idx, m in enumerate(messages[:5], 1):
                    sender = m.get("from", "Unknown")[:25]
                    subject = m.get("subject", "No subject")[:30]
                    mid = m.get("id")
                    mail_list_text += f"{idx}. 📩 *ពី:* `{sender}`\n   📌 *កម្មវត្ថុ:* {subject}\n\n"
                    kb_rows.append([InlineKeyboardButton(f"📖 អានសារ #{idx}: {subject[:20]}", callback_data=f"mail_read_{mid}")])
            else:
                mail_list_text = "📭 *Inbox ទំនេរ (មិនទាន់មានសារថ្មីនៅឡើយទេ)*\n_នៅពេលមានគេផ្ញើអ៊ីមែល ឬកូដ OTP មក វានឹងបង្ហាញនៅទីនេះភ្លាមៗ!_"

            text = (
                "📧 *[10-Minute Disposable Email - អ៊ីមែលបណ្តោះអាសន្ន]* 🛡️\n\n"
                f"📬 *អាសយដ្ឋាន Email របស់អ្នក៖*\n`{curr_email}`\n\n"
                "💡 _ចុចលើ Email ខាងលើដើម្បី Copy យកទៅចុះឈ្មោះ ឬទទួលកូដ OTP ដោយមិនបារម្ភរឿង Spam ក្នុង Email ពិតប្រាកដ!_\n\n"
                f"{mail_list_text}"
            )
            kb_rows.append([InlineKeyboardButton("🔙 Menu ដើម", callback_data="btn_back_main")])
            await query.edit_message_text(text=text, reply_markup=InlineKeyboardMarkup(kb_rows), parse_mode="Markdown")

        elif data == "mail_new":
            await query.answer("កំពុងបង្កើត Email ថ្មី...")
            from services.temp_mail_service import generate_temp_email
            new_email = await generate_temp_email(chat_id)
            text = (
                "📧 *[10-Minute Disposable Email - អ៊ីមែលបណ្តោះអាសន្ន]* 🛡️\n\n"
                f"📬 *អាសយដ្ឋាន Email ថ្មីរបស់អ្នក៖*\n`{new_email}`\n\n"
                "💡 _ចុចលើ Email ខាងលើដើម្បី Copy យកទៅចុះឈ្មោះ ឬទទួលកូដ OTP ភ្លាមៗ!_\n\n"
                "📭 *Inbox ទំនេរ (មិនទាន់មានសារថ្មី)*"
            )
            kb = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("🔄 ពិនិត្យសារថ្មី (Check Inbox)", callback_data="mail_refresh"),
                    InlineKeyboardButton("🆕 បង្កើត Email ថ្មី", callback_data="mail_new"),
                ],
                [InlineKeyboardButton("🔙 Menu ដើម", callback_data="btn_back_main")]
            ])
            await query.edit_message_text(text=text, reply_markup=kb, parse_mode="Markdown")

        elif data.startswith("mail_read_"):
            await query.answer("កំពុងអានសារ...")
            msg_id = int(data.replace("mail_read_", ""))
            from services.temp_mail_service import fetch_message_content
            ok, mdata = await fetch_message_content(chat_id, msg_id)
            if ok:
                sender = mdata.get("from", "Unknown")
                subject = mdata.get("subject", "No subject")
                date = mdata.get("date", "")
                otp = mdata.get("extracted_otp")
                body = (mdata.get("textBody") or mdata.get("body") or "")[:800]

                otp_banner = f"🔑 *កូដផ្ទៀងផ្ទាត់ (OTP Code)៖* `{otp}` ⚡\n\n" if otp else ""

                mail_read_text = (
                    "📩 *[ខ្លឹមសារអ៊ីមែលដែលបានទទួល]* ✨\n\n"
                    f"{otp_banner}"
                    f"👤 *ពី:* `{sender}`\n"
                    f"📌 *កម្មវត្ថុ:* `{subject}`\n"
                    f"🕒 *កាលបរិច្ឆេទ:* `{date}`\n\n"
                    "📄 *ខ្លឹមសារសារ៖*\n"
                    f"```\n{body}\n```"
                )
            else:
                mail_read_text = "❌ មិនអាចទាញយកខ្លឹមសារសារនេះបានទេ។"

            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("📬 ត្រឡប់ទៅ Inbox", callback_data="btn_tempmail")],
                [InlineKeyboardButton("🔙 Menu ដើម", callback_data="btn_back_main")]
            ])
            await query.edit_message_text(text=mail_read_text, reply_markup=kb, parse_mode="Markdown")
    except Exception as e:
        logger.warning(f"Callback error: {e}")
        try:
            await query.answer()
        except Exception:
            pass

# -------------------------------------------------------------
# V6 Media Superpowers & AI Next-Gen Command Handlers
# -------------------------------------------------------------

async def imagine_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generate high-resolution AI art from prompt: /imagine <prompt>."""
    prompt = " ".join(context.args) if context.args else ""
    if not prompt and update.message and update.message.reply_to_message:
        prompt = update.message.reply_to_message.text or update.message.reply_to_message.caption or ""

    if not prompt:
        tip = (
            "🎨 *[AI Image Generator - បង្កើតរូបភាព AI]* ✨\n\n"
            "សូមវាយ៖ `/imagine <ពិពណ៌នារូបភាពដែលអ្នកចង់បាន>`\n\n"
            "• ឧទាហរណ៍៖ `/imagine រថយន្តទំនើបបើកកាត់ប្រាសាទអង្គរវត្តពេលថ្ងៃលិច`\n"
            "• ឧទាហរណ៍៖ `/imagine cute anime girl reading book in cozy coffee shop 4k cinematic`\n"
            "• ឧទាហរណ៍៖ `/imagine នាគរាជខ្មែរហោះលើផ្ទៃមេឃពណ៌មាស`\n\n"
            "💡 _គាំទ្រទាំងភាសាខ្មែរ និងអង់គ្លេស ដោយប្រើម៉ូដែល FLUX.1 Ultra HD ឥតគិតថ្លៃ!_ 🚀"
        )
        await safe_reply_text(update.message, tip)
        return

    status_msg = await update.message.reply_text(
        f"🎨 *AI កំពុងបង្កើតរូបភាពតាមការពិពណ៌នារបស់អ្នក...*\n"
        f"💡 _\"{prompt[:60]}...\"_\n\n"
        f"សូមរង់ចាំប្រហែល ៥ ទៅ ១០ វិនាទី! 🚀",
        parse_mode="Markdown"
    )
    await update.message.chat.send_action("upload_photo")

    try:
        from services.imagine_service import generate_ai_image
        img_bytes, orig_p, exp_p = await generate_ai_image(prompt)
        if not img_bytes:
            await safe_edit_text(status_msg, "❌ បរាជ័យក្នុងការបង្កើតរូបភាព។ សូមសាកល្បងផ្លាស់ប្តូរពាក្យពិពណ៌នា (Prompt) ម្តងទៀត។")
            return

        import io
        img_io = io.BytesIO(img_bytes)
        img_io.name = "generated_ai_art.jpg"

        caption = (
            f"🎨 *រូបភាព AI បង្កើតបានសម្រេច!* ✨\n\n"
            f"📝 *Prompt ដើម:* `{orig_p[:100]}`\n"
            f"🔍 *Enhanced Prompt:* _{exp_p[:140]}_\n\n"
            f"✨ បង្កើតដោយ Smart Assistant Bot 🚀"
        )

        buttons = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("💎 2K HD", callback_data="btn_upscale_2k"),
                InlineKeyboardButton("🔥 4K Ultra", callback_data="btn_upscale_4k"),
                InlineKeyboardButton("🌌 8K Super-Res", callback_data="btn_upscale_8k"),
            ],
            [
                InlineKeyboardButton("💧 ដាក់ Watermark", callback_data="btn_watermark_info"),
                InlineKeyboardButton("🔙 Menu ដើម", callback_data="btn_back_main")
            ]
        ])

        await update.message.reply_photo(
            photo=img_io,
            caption=caption,
            reply_markup=buttons,
            parse_mode="Markdown"
        )
        try:
            await status_msg.delete()
        except Exception:
            pass

    except Exception as e:
        logger.error(f"Error in imagine command: {e}")
        await safe_edit_text(status_msg, f"❌ កំហុសបច្ចេកទេសក្នុងការបង្កើតរូបភាព៖ {str(e)[:120]}")

async def summarize_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Summarize long YouTube video/podcast into Khmer takeaways: /summarize <url>."""
    url = " ".join(context.args) if context.args else ""
    if not url and update.message and update.message.reply_to_message:
        candidate = update.message.reply_to_message.text or update.message.reply_to_message.caption or ""
        from services.video_downloader import extract_video_url
        url = extract_video_url(candidate) or ""

    if not url:
        from services.video_downloader import extract_video_url
        url = extract_video_url(update.message.text or "") or ""

    if not url:
        tip = (
            "📝 *[YouTube AI Video Summarizer - សង្ខេបវីដេអូ]* ✨\n\n"
            "ជួយសន្សំពេលវេលាដោយមិនបាច់មើលវីដេអូរាប់ម៉ោង! AI នឹងស្ដាប់ និងសង្ខេបចំណុចសំខាន់ៗជាភាសាខ្មែរជូនភ្លាមៗ!\n\n"
            "👉 *របៀបប្រើប្រាស់៖*\n"
            "`/summarize <Link វីដេអូ YouTube>`\n\n"
            "• ឧទាហរណ៍៖ `/summarize https://www.youtube.com/watch?v=...`\n"
            "💡 _ឬគ្រាន់តែ Reply លើ Link វីដេអូ ដោយវាយពាក្យ:_ `/summarize`"
        )
        await safe_reply_text(update.message, tip)
        return

    status_msg = await update.message.reply_text(
        "🧠 *AI កំពុងទាញយក Transcript និងវិភាគខ្លឹមសារវីដេអូ...*\n"
        "សូមរង់ចាំប្រហែល ៥ ទៅ ១០ វិនាទី! 🚀",
        parse_mode="Markdown"
    )
    await update.message.chat.send_action("typing")

    try:
        from services.summarizer_service import summarize_video_ai
        summary_result = await summarize_video_ai(url)
        await safe_edit_text(status_msg, summary_result)
    except Exception as e:
        logger.error(f"Error in summarize command: {e}")
        await safe_edit_text(status_msg, f"❌ កំហុសក្នុងការសង្ខេបវីដេអូ៖ {str(e)[:120]}")

async def sub_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Download video subtitles and translate to Khmer (.srt file): /sub <url>."""
    url = " ".join(context.args) if context.args else ""
    if not url and update.message and update.message.reply_to_message:
        candidate = update.message.reply_to_message.text or update.message.reply_to_message.caption or ""
        from services.video_downloader import extract_video_url
        url = extract_video_url(candidate) or ""

    if not url:
        from services.video_downloader import extract_video_url
        url = extract_video_url(update.message.text or "") or ""

    if not url:
        tip = (
            "📑 *[Auto-Subtitles & Khmer Translation - ចំណងជើងរង]* ✨\n\n"
            "ទាញយក Subtitle ពី YouTube រួចបកប្រែជាភាសាខ្មែរ និងបង្កើតជា File `.srt` សម្រាប់យកទៅមើលជាមួយវីដេអូបានភ្លាមៗ!\n\n"
            "👉 *របៀបប្រើប្រាស់៖*\n"
            "`/sub <Link វីដេអូ YouTube>`\n\n"
            "• ឧទាហរណ៍៖ `/sub https://www.youtube.com/watch?v=...`\n"
            "💡 _ឬ Reply លើ Link វីដេអូ ដោយវាយពាក្យ:_ `/sub`"
        )
        await safe_reply_text(update.message, tip)
        return

    status_msg = await update.message.reply_text(
        "📑 *កំពុងទាញយក Subtitles និងប្រើប្រាស់ AI បកប្រែជាភាសាខ្មែរ...*\n"
        "សូមរង់ចាំបន្តិចណា៎! 🚀",
        parse_mode="Markdown"
    )
    await update.message.chat.send_action("typing")

    try:
        from services.subtitle_service import generate_khmer_subtitles
        sub_res = await generate_khmer_subtitles(url)
        if not sub_res.get("success"):
            await safe_edit_text(status_msg, f"❌ បរាជ័យ៖ {sub_res.get('error')}")
            return

        file_path = sub_res["file_path"]
        caption = (
            f"📑 *ចំណងជើងរងជាភាសាខ្មែរ (Khmer Subtitles)* ✨\n\n"
            f"🎬 *វីដេអូ:* {sub_res['title'][:50]}\n"
            f"🔢 *ចំនួនឃ្លា:* {sub_res['cues_count']} ឃ្លា\n\n"
            f"📝 *គំរូ Subtitle ដើមវីដេអូ៖*\n{sub_res['preview_text']}\n\n"
            f"✨ បកប្រែដោយ Smart Assistant Bot 🚀"
        )

        with open(file_path, "rb") as srt_file:
            await update.message.reply_document(
                document=srt_file,
                filename=sub_res["filename"],
                caption=caption,
                parse_mode="Markdown"
            )

        try:
            await status_msg.delete()
        except Exception:
            pass

        from services.video_downloader import cleanup_file
        cleanup_file(file_path)

    except Exception as e:
        logger.error(f"Error in sub command: {e}")
        await safe_edit_text(status_msg, f"❌ កំហុសក្នុងការទាញយក Subtitle៖ {str(e)[:120]}")

async def playlist_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Download entire YouTube playlist batch as MP3 & auto-archive to @Song182: /playlist <url>."""
    url = " ".join(context.args) if context.args else ""
    if not url and update.message and update.message.reply_to_message:
        candidate = update.message.reply_to_message.text or update.message.reply_to_message.caption or ""
        from services.video_downloader import extract_video_url
        url = extract_video_url(candidate) or ""

    if not url:
        tip = (
            "🎧 *[Playlist Batch Downloader - ទាញយកចម្រៀងទាំងកញ្ចប់]* 🎶\n\n"
            "ទាញយកបទចម្រៀងទាំងអស់ក្នុង YouTube Playlist មួយ ជា File MP3 320kbps និង Upload រក្សាទុកក្នុង Channel `@Song182` ដោយស្វ័យប្រវត្តិ!\n\n"
            "👉 *របៀបប្រើប្រាស់៖*\n"
            "`/playlist <Link YouTube Playlist>`\n\n"
            "• ឧទាហរណ៍៖ `/playlist https://www.youtube.com/playlist?list=...`\n"
            "💡 _កំណត់ទាញយកអតិបរមា ១០ ទៅ ១៥ បទក្នុងពេលតែមួយ ដើម្បីការពារកុំឱ្យជាប់ Spam Telegram!_"
        )
        await safe_reply_text(update.message, tip)
        return

    status_msg = await update.message.reply_text(
        "⏳ *កំពុងទាញយកព័ត៌មាន Playlist... សូមរង់ចាំបន្តិចណា៎!* 🎶",
        parse_mode="Markdown"
    )
    await update.message.chat.send_action("typing")

    try:
        from services.playlist_service import process_and_archive_playlist
        await process_and_archive_playlist(
            bot=context.bot,
            chat_id=update.effective_chat.id,
            user=update.effective_user,
            playlist_url=url,
            status_msg=status_msg,
            max_items=10
        )
    except Exception as e:
        logger.error(f"Error in playlist command: {e}")
        await safe_edit_text(status_msg, f"❌ កំហុសក្នុងការទាញយក Playlist៖ {str(e)[:120]}")

async def trim_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Trim video by replying to a video message: /trim <start> <end> (e.g. /trim 00:10 00:45)."""
    reply_msg = update.message.reply_to_message if update.message else None
    if not reply_msg or not (reply_msg.video or reply_msg.animation or reply_msg.document):
        tip = (
            "✂️ *[Video Trimmer - កាត់វីដេអូក្នុង Chat]* 🎬\n\n"
            "សូមធ្វើការ **Reply លើវីដេអូណាមួយ** រួចវាយបញ្ជា៖\n"
            "`/trim <ម៉ោងចាប់ផ្ដើម> <ម៉ោងបញ្ចប់>`\n\n"
            "• ឧទាហរណ៍៖ `/trim 00:10 00:35` (កាត់ពីវិនាទី ១០ ដល់ ៣៥)\n"
            "• ឧទាហរណ៍៖ `/trim 1:15 2:00` (កាត់ពីនាទី ១:១៥ ដល់ ២:០០)\n"
            "• ឧទាហរណ៍៖ `/trim 5 25` (កាត់ពីវិនាទី ៥ ដល់ ២៥)\n\n"
            "💡 _ចំណាំ៖ រយៈពេលកាត់អតិបរមាត្រឹម ៥ នាទី។_"
        )
        await safe_reply_text(update.message, tip)
        return

    args = context.args or []
    if len(args) < 2:
        await safe_reply_text(update.message, "⚠️ សូមបញ្ជាក់ម៉ោងចាប់ផ្ដើម និងម៉ោងបញ្ចប់! ឧ. `/trim 00:10 00:45`")
        return

    start_t, end_t = args[0], args[1]
    status_msg = await update.message.reply_text(
        f"✂️ *កំពុងទាញយក និងកាត់វីដេអូពី {start_t} ដល់ {end_t}...*\n"
        f"សូមរង់ចាំបន្តិចណា៎! 🚀",
        parse_mode="Markdown"
    )
    await update.message.chat.send_action("upload_video")

    from config import DOWNLOAD_DIR
    import uuid
    from services.video_downloader import cleanup_file

    media_obj = reply_msg.video or reply_msg.animation or reply_msg.document
    unique_id = uuid.uuid4().hex[:8]
    temp_in = DOWNLOAD_DIR / f"raw_trim_{unique_id}.mp4"

    try:
        tg_file = await context.bot.get_file(media_obj.file_id)
        await tg_file.download_to_drive(str(temp_in))

        from services.video_editor_service import trim_video
        out_path, err = trim_video(str(temp_in), start_t, end_t)
        if err or not out_path or not os.path.exists(out_path):
            await safe_edit_text(status_msg, f"❌ បរាជ័យក្នុងការកាត់វីដេអូ៖ {err}")
            return

        with open(out_path, "rb") as vf:
            await update.message.reply_video(
                video=vf,
                caption=f"✂️ *វីដេអូកាត់រួចរាល់ ({start_t} ➔ {end_t})* ✨\n\n✨ កាត់ដោយ Smart Assistant Bot 🚀",
                parse_mode="Markdown"
            )

        try:
            await status_msg.delete()
        except Exception:
            pass

        cleanup_file(out_path)
    except Exception as e:
        logger.error(f"Error trimming video: {e}")
        await safe_edit_text(status_msg, f"❌ កំហុសបច្ចេកទេស៖ {str(e)[:120]}")
    finally:
        cleanup_file(str(temp_in))

async def gif_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Convert a video clip to an animated looping GIF: reply with /gif."""
    reply_msg = update.message.reply_to_message if update.message else None
    if not reply_msg or not (reply_msg.video or reply_msg.animation or reply_msg.document):
        tip = (
            "🎞️ *[GIF Maker - បម្លែងវីដេអូទៅជា GIF]* ✨\n\n"
            "សូមធ្វើការ **Reply លើវីដេអូណាមួយ** រួចវាយបញ្ជា៖\n"
            "`/gif`\n\n"
            "Bot នឹងបម្លែងវីដេអូនោះទៅជា Animated Looping GIF គុណភាពខ្ពស់ គ្មានសំឡេង សម្រាប់ផ្ញើលេងក្នុង Telegram បានភ្លាមៗ! 🚀"
        )
        await safe_reply_text(update.message, tip)
        return

    status_msg = await update.message.reply_text(
        "🎞️ *កំពុងបម្លែងវីដេអូទៅជា Animated GIF...*\n"
        "សូមរង់ចាំបន្តិចណា៎! 🚀",
        parse_mode="Markdown"
    )
    await update.message.chat.send_action("upload_video")

    from config import DOWNLOAD_DIR
    import uuid
    from services.video_downloader import cleanup_file

    media_obj = reply_msg.video or reply_msg.animation or reply_msg.document
    unique_id = uuid.uuid4().hex[:8]
    temp_in = DOWNLOAD_DIR / f"raw_gif_{unique_id}.mp4"

    try:
        tg_file = await context.bot.get_file(media_obj.file_id)
        await tg_file.download_to_drive(str(temp_in))

        from services.video_editor_service import convert_video_to_gif
        out_path, err = convert_video_to_gif(str(temp_in), max_duration=15)
        if err or not out_path or not os.path.exists(out_path):
            await safe_edit_text(status_msg, f"❌ បរាជ័យក្នុងការបម្លែងជា GIF៖ {err}")
            return

        with open(out_path, "rb") as gf:
            await update.message.reply_animation(
                animation=gf,
                caption="🎞️ *បានបម្លែងជា Animated GIF រួចរាល់!* ✨\n\n✨ Smart Assistant Bot 🚀",
                parse_mode="Markdown"
            )

        try:
            await status_msg.delete()
        except Exception:
            pass

        cleanup_file(out_path)
    except Exception as e:
        logger.error(f"Error converting to gif: {e}")
        await safe_edit_text(status_msg, f"❌ កំហុសបច្ចេកទេស៖ {str(e)[:120]}")
    finally:
        cleanup_file(str(temp_in))

async def botserver_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Guide on how to configure and run Telegram Local Bot API Server for 2GB uploads."""
    from config import LOCAL_BOT_API_URL, MAX_FILE_SIZE_MB
    status = f"✅ កំពុងដំណើរការ: `{LOCAL_BOT_API_URL}` (ដែនកំណត់: {MAX_FILE_SIZE_MB} MB)" if LOCAL_BOT_API_URL else "⚠️ បច្ចុប្បន្នប្រើ Telegram Cloud Bot API ផ្លូវការ (ដែនកំណត់: 50 MB)"

    guide = (
        "🖥️ *[Telegram Local Bot API Server - ផ្ញើ File បានដល់ 2 GB]* 🚀\n\n"
        f"📊 *ស្ថានភាពបច្ចុប្បន្ន៖* {status}\n\n"
        "💡 *តើអ្វីជា Local Bot API Server?*\n"
        "Telegram អនុញ្ញាតឱ្យយើង Run Server Bot API ដោយខ្លួនឯង (Self-hosted)។ នៅពេលប្រើ Local Bot API Server នោះ Bot នឹងអាច៖\n"
        "• 📤 Upload វីដេអូ 4K & 8K បានទំហំរហូតដល់ **2,000 MB (2 GB)** ផ្ទាល់ក្នុង Chat!\n"
        "• ⚡ ល្បឿន Upload/Download លឿនជាងមុនទ្វេដង (Local Loopback)\n\n"
        "🐳 *របៀប Run តាម Docker (ត្រឹមតែ ១ បន្ទាត់):*\n"
        "```bash\n"
        "docker run -d -p 8081:8081 --name telegram-bot-api \\\n"
        "  -v /var/lib/telegram-bot-api:/var/lib/telegram-bot-api \\\n"
        "  aiogram/telegram-bot-api:latest \\\n"
        "  --api-id=<YOUR_TELEGRAM_API_ID> \\\n"
        "  --api-hash=<YOUR_TELEGRAM_API_HASH> \\\n"
        "  --local\n"
        "```\n\n"
        "⚙️ *ការភ្ជាប់ជាមួយ Bot នេះ៖*\n"
        "គ្រាន់តែបើក file `.env` រួចបន្ថែម៖\n"
        "`LOCAL_BOT_API_URL=\"http://localhost:8081\"`\n\n"
        "Bot នឹងដំណើរការទាញយក និងផ្ញើវីដេអូកម្រិត 4K/8K ដល់ទំហំ 2GB ដោយស្វ័យប្រវត្តិ! ✨"
    )
    await safe_reply_text(update.message, guide)

async def persona_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Command /persona or /mode to quickly change Persona."""
    msg = (
        "🎭 *ជ្រើសរើស Persona / Role សម្រាប់គណនីរបស់អ្នក* ✨\n\n"
        "ជ្រើសរើសប្រភេទការងាររបស់អ្នកដើម្បីឱ្យ Bot បង្ហាញប៊ូតុងមុខងារដែលត្រូវនឹងតម្រូវការបំផុត៖\n\n"
        "🎓 *១. របៀបសិស្ស/និស្សិត (Student Mode):*\n"
        "• ដោះស្រាយលំហាត់ AI, Chat with PDF, បកប្រែភាសា Pro, ពិនិត្យអក្ខរាវិរុទ្ធ, សង្ខេប YouTube\n\n"
        "💼 *២. របៀបអាជីវកម្ម/លក់ដូរ (Business Mode):*\n"
        "• ស្កេនវិក្កយបត្រ AI, ចំណូល-ចំណាយ Budget, ក្រាហ្វិក Donut Chart, Watermark ទំនិញ, KHQR, តម្លៃមាស/សាំង\n\n"
        "🎬 *៣. របៀបអ្នកកាត់ត & Media (Creator Mode):*\n"
        "• ទាញយក 4K/8K, YouTube Playlist, កាត់វីដេអូ /trim, GIF Maker, បង្កើតរូប AI /imagine, Subtitle ខ្មែរ\n\n"
        "🌐 *៤. បង្ហាញទាំងអស់ (All-in-One Slider):*\n"
        "• ប្រើប្រាស់ Paginated Slider Menu ៣ ទំព័រ [1/3] ដូចធម្មតា\n\n"
        "👇 _សូមចុចជ្រើសរើសខាងក្រោម៖_"
    )
    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🎓 របៀបសិស្ស/និស្សិត", callback_data="set_persona_student"),
            InlineKeyboardButton("💼 របៀបអាជីវកម្ម/លក់ដូរ", callback_data="set_persona_business"),
        ],
        [
            InlineKeyboardButton("🎬 របៀបអ្នកកាត់ត & Media", callback_data="set_persona_creator"),
            InlineKeyboardButton("🌐 បង្ហាញទាំងអស់ (Slider)", callback_data="set_persona_all"),
        ],
        [
            InlineKeyboardButton("🔙 Menu ដើម", callback_data="btn_back_main")
        ]
    ])
    await send_clean_response(update, context, msg, reply_markup=kb, parse_mode="Markdown")

# -------------------------------------------------------------
# Level Master: Next-Gen AI Superpower Command Handlers
# -------------------------------------------------------------

async def event_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Parse natural language schedule and auto-sync with Google Calendar & 60-min advance reminder: /event <text>."""
    chat = update.effective_chat
    user_text = " ".join(context.args) if context.args else ""
    if not user_text and update.message and update.message.reply_to_message:
        user_text = update.message.reply_to_message.text or update.message.reply_to_message.caption or ""

    if not user_text:
        tip = (
            "📅 *[Google Calendar Auto-Sync - ការណែនាំ]* ✨\n\n"
            "គ្រាន់តែប្រាប់ Bot ពីការណាត់ជួបជាភាសាខ្មែរធម្មតា ➔ AI នឹងរៀបចំ Event ចូល Google Calendar និងដាស់តឿនមុន ៦០ នាទីដោយស្វ័យប្រវត្តិ!\n\n"
            "👉 *របៀបប្រើប្រាស់៖*\n"
            "វាយ៖ `/event <ព័ត៌មានណាត់ជួប>` ឬ `/schedule <ព័ត៌មាន>`\n\n"
            "• ឧទាហរណ៍៖ `/event ស្អែកម៉ោង ២ រសៀល ណាត់ជួបអតិថិជននៅ Brown Bokor`\n"
            "• ឧទាហរណ៍៖ `/event ថ្ងៃចន្ទសប្តាហ៍ក្រោយ ម៉ោង 9:00 ព្រឹក ប្រជុំគម្រោងក្រុមហ៊ុន`\n"
            "• ឧទាហរណ៍៖ `/event ថ្ងៃទី 28 ខែវិច្ឆិកា ម៉ោង 7 យប់ ញ៉ាំបាយជុំគ្នា`\n\n"
            "💡 _ឬគ្រាន់តែ Reply លើសារណាមួយដោយវាយពាក្យ:_ `/event`"
        )
        await safe_reply_text(update.message, tip)
        return

    status_msg = await update.message.reply_text("🧠 *AI កំពុងវិភាគ និងរៀបចំ Event ចូល Calendar...*", parse_mode="Markdown")
    await update.message.chat.send_action("typing")

    try:
        from services.calendar_service import parse_and_create_calendar_event
        import io
        ok, msg_text, gcal_url, ics_str = await parse_and_create_calendar_event(user_text, chat.id)
        if not ok:
            await safe_edit_text(status_msg, msg_text)
            return

        buttons = []
        if gcal_url:
            buttons.append([InlineKeyboardButton("📅 បញ្ចូលក្នុង Google Calendar ភ្លាមៗ", url=gcal_url)])
        buttons.append([InlineKeyboardButton("🔙 Menu ដើម", callback_data="btn_back_main")])

        await safe_edit_text(status_msg, msg_text, reply_markup=InlineKeyboardMarkup(buttons))

        # Send .ICS file for Apple/Outlook/Google 1-tap import
        if ics_str:
            ics_file = io.BytesIO(ics_str.encode("utf-8"))
            ics_file.name = "event_invite.ics"
            await update.message.reply_document(
                document=ics_file,
                filename="event_invite.ics",
                caption="📎 *ឯកសារប្រតិទិន iCalendar (.ICS)*\n_ចុចលើ File នេះដើម្បី Add ចូល Calendar លើទូរស័ព្ទភ្លាមៗ!_",
                parse_mode="Markdown"
            )
    except Exception as e:
        logger.error(f"Error in event_command: {e}")
        await safe_edit_text(status_msg, f"❌ កំហុសបច្ចេកទេស៖ {str(e)[:120]}")

async def word_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Convert photo / scanned document into editable Microsoft Word (.docx): /word."""
    chat = update.effective_chat
    img_bytes = None

    # Check if photo attached directly
    if update.message.photo:
        photo = update.message.photo[-1]
        tg_file = await context.bot.get_file(photo.file_id)
        img_bytes = bytes(await tg_file.download_as_bytearray())
    # Check if replied to a photo
    elif update.message.reply_to_message and update.message.reply_to_message.photo:
        photo = update.message.reply_to_message.photo[-1]
        tg_file = await context.bot.get_file(photo.file_id)
        img_bytes = bytes(await tg_file.download_as_bytearray())
    # Check cached last photo
    elif context.user_data.get("last_photo_bytes"):
        img_bytes = context.user_data.get("last_photo_bytes")

    if not img_bytes:
        tip = (
            "📝 *[Smart Document Converter - រូបថត ➔ Word (.docx)]* ✨\n\n"
            "បម្លែងរូបថតក្រដាសឯកសារ សៀវភៅ ឬអត្ថបទឱ្យក្លាយជា File Word ដែលអាច Edit បាន មិនបាច់អង្គុយវាយឡើងវិញ!\n\n"
            "👉 *របៀបប្រើប្រាស់៖*\n"
            "• ផ្ញើរូបភាពដោយភ្ជាប់ Caption៖ `/word` ឬ `/docx`\n"
            "• ឬគ្រាន់តែ Reply លើរូបថតឯកសារដោយវាយពាក្យ៖ `/word`"
        )
        await safe_reply_text(update.message, tip)
        return

    status_msg = await update.message.reply_text("📝 *AI កំពុងស្កេន OCR និងរៀបចំឯកសារ Word (.docx)...*\nសូមរង់ចាំបន្តិចណា៎! 🚀", parse_mode="Markdown")
    await update.message.chat.send_action("upload_document")

    try:
        from services.doc_converter_service import convert_image_to_docx
        import io
        docx_bytes, filename, summary = await convert_image_to_docx(img_bytes)
        if docx_bytes:
            await update.message.reply_document(
                document=io.BytesIO(docx_bytes),
                filename=filename,
                caption=f"📝 *បានបម្លែងជា Word (.docx) ជោគជ័យ!* ✨\n\n_{summary}_\n\n🤖 Smart Assistant Bot 🚀",
                parse_mode="Markdown"
            )
            try:
                await status_msg.delete()
            except Exception:
                pass
        else:
            await safe_edit_text(status_msg, f"❌ {summary}")
    except Exception as e:
        logger.error(f"Error in word_command: {e}")
        await safe_edit_text(status_msg, f"❌ កំហុសក្នុងការបម្លែងជា Word៖ {str(e)[:120]}")

async def sheet_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Convert photo / receipt / table into editable Microsoft Excel (.xlsx): /sheet."""
    chat = update.effective_chat
    img_bytes = None

    if update.message.photo:
        photo = update.message.photo[-1]
        tg_file = await context.bot.get_file(photo.file_id)
        img_bytes = bytes(await tg_file.download_as_bytearray())
    elif update.message.reply_to_message and update.message.reply_to_message.photo:
        photo = update.message.reply_to_message.photo[-1]
        tg_file = await context.bot.get_file(photo.file_id)
        img_bytes = bytes(await tg_file.download_as_bytearray())
    elif context.user_data.get("last_photo_bytes"):
        img_bytes = context.user_data.get("last_photo_bytes")

    if not img_bytes:
        tip = (
            "📊 *[Smart Table OCR - រូបថតតារាង ➔ Excel (.xlsx)]* ✨\n\n"
            "ស្កេនទាញយកតារាងលេខ វិក្កយបត្រ ឬបញ្ជីទំនិញពីរូបថត បម្លែងទៅជា File Excel មានជួរឈរនិងជួរដេកត្រឹមត្រូវ!\n\n"
            "👉 *របៀបប្រើប្រាស់៖*\n"
            "• ផ្ញើរូបភាពដោយភ្ជាប់ Caption៖ `/sheet`\n"
            "• ឬគ្រាន់តែ Reply លើរូបថតតារាងដោយវាយពាក្យ:_ `/sheet`"
        )
        await safe_reply_text(update.message, tip)
        return

    status_msg = await update.message.reply_text("📊 *AI កំពុងស្កេនទិន្នន័យ និងរៀបចំ File Excel (.xlsx)...*\nសូមរង់ចាំបន្តិចណា៎! 🚀", parse_mode="Markdown")
    await update.message.chat.send_action("upload_document")

    try:
        from services.doc_converter_service import convert_image_to_xlsx
        import io
        xlsx_bytes, filename, summary = await convert_image_to_xlsx(img_bytes)
        if xlsx_bytes:
            await update.message.reply_document(
                document=io.BytesIO(xlsx_bytes),
                filename=filename,
                caption=f"📊 *បានបម្លែងជា Excel (.xlsx) ជោគជ័យ!* ✨\n\n_{summary}_\n\n🤖 Smart Assistant Bot 🚀",
                parse_mode="Markdown"
            )
            try:
                await status_msg.delete()
            except Exception:
                pass
        else:
            await safe_edit_text(status_msg, f"❌ {summary}")
    except Exception as e:
        logger.error(f"Error in sheet_command: {e}")
        await safe_edit_text(status_msg, f"❌ កំហុសក្នុងការបម្លែងជា Excel៖ {str(e)[:120]}")

async def shorts_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Automatically find and clip the most viral 30-60 second hook from YouTube video: /shorts <url>."""
    url = " ".join(context.args) if context.args else ""
    if not url and update.message and update.message.reply_to_message:
        candidate = update.message.reply_to_message.text or update.message.reply_to_message.caption or ""
        from services.video_downloader import extract_video_url
        url = extract_video_url(candidate) or ""

    if not url:
        from services.video_downloader import extract_video_url
        url = extract_video_url(update.message.text or "") or ""

    if not url:
        tip = (
            "✂️ *[Viral Shorts Auto-Clipper - កាត់វីដេអូខ្លី]* 🎬\n\n"
            "ដាក់ Link វីដេអូ YouTube វែង ➔ AI ស្វែងរកវិនាទីដែលជក់ចិត្តបំផុត រួចកាត់ជាវីដេអូខ្លី ៣០ ទៅ ៦០ វិនាទីសម្រាប់ TikTok/Reels!\n\n"
            "👉 *របៀបប្រើប្រាស់៖*\n"
            "`/shorts <Link YouTube>` ឬ `/clip <Link YouTube>`\n\n"
            "• ឧទាហរណ៍៖ `/shorts https://www.youtube.com/watch?v=...`\n"
            "💡 _ឬគ្រាន់តែ Reply លើសារដែលមាន Link វីដេអូ ដោយវាយពាក្យ:_ `/shorts`"
        )
        await safe_reply_text(update.message, tip)
        return

    status_msg = await update.message.reply_text(
        "🧠 *AI កំពុងស្កេនរកឈុតឆាកល្អបំផុត និង Render វីដេអូខ្លី Viral Shorts...*\n"
        "សូមរង់ចាំប្រហែល ១៥ ទៅ ៣០ វិនាទី! 🚀",
        parse_mode="Markdown"
    )
    await update.message.chat.send_action("upload_video")

    try:
        from services.shorts_clipper_service import auto_clip_viral_shorts
        ok, clip_path, hook_title, meta = await auto_clip_viral_shorts(url)
        if not ok or not clip_path or not os.path.exists(clip_path):
            await safe_edit_text(status_msg, hook_title)
            return

        caption = (
            f"✂️ *[Viral Short Clip រួចរាល់!]* 🎬\n\n"
            f"🔥 *ចំណងជើង:* **{hook_title}**\n"
            f"🕒 *ចន្លោះពេល:* `{meta.get('start_time')} - {meta.get('end_time')}` ({meta.get('clip_duration')} វិនាទី)\n"
            f"💡 *មូលហេតុទាក់ទាញ:* _{meta.get('viral_reason')}_\n\n"
            f"✨ រួចរាល់សម្រាប់យកទៅបង្ហោះលើ TikTok & Facebook Reels! 🚀"
        )

        with open(clip_path, "rb") as vf:
            await update.message.reply_video(
                video=vf,
                caption=caption,
                parse_mode="Markdown"
            )

        try:
            await status_msg.delete()
        except Exception:
            pass

        try:
            os.remove(clip_path)
        except Exception:
            pass

    except Exception as e:
        logger.error(f"Error in shorts_command: {e}")
        await safe_edit_text(status_msg, f"❌ កំហុសក្នុងការកាត់វីដេអូ Viral Shorts៖ {str(e)[:120]}")

async def scan_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Scan suspicious link, URL, or forwarded message for phishing, scams, and banking malware: /scan <target>."""
    target = " ".join(context.args) if context.args else ""
    if not target and update.message and update.message.reply_to_message:
        target = update.message.reply_to_message.text or update.message.reply_to_message.caption or ""

    if not target:
        tip = (
            "🔍 *[Phishing & Scam Link Scanner - ស្កេន Link បោក]* 🛡️\n\n"
            "ត្រួតពិនិត្យសុវត្ថិភាពតំណភ្ជាប់ (Link) គេហទំព័របោកប្រាស់ លួចគណនី Telegram ឬមេរោគ APK ធនាគារក្លែងក្លាយ!\n\n"
            "👉 *របៀបប្រើប្រាស់៖*\n"
            "• វាយ៖ `/scan <Link ឬអត្ថបទសារ>`\n"
            "• ឧទាហរណ៍៖ `/scan https://aba-fake-login.com`\n"
            "• ឧទាហរណ៍៖ `/scan ចូលរួមបោះឆ្នោតឈ្នះរង្វាន់ $500`\n\n"
            "💡 _ឬគ្រាន់តែ Forward សារគួរឱ្យសង្ស័យចូលក្នុង Bot រួចវាយ:_ `/scan`"
        )
        await safe_reply_text(update.message, tip)
        return

    status_msg = await update.message.reply_text("🔍 *កំពុងស្កេនវិភាគសុវត្ថិភាព Link និងត្រួតពិនិត្យ Phishing/Scam...* 🛡️", parse_mode="Markdown")
    await update.message.chat.send_action("typing")

    try:
        from services.scam_scanner_service import scan_link_or_text
        report = await scan_link_or_text(target)

        score_bar = "🟢" if report["risk_score"] < 25 else ("🟡" if report["risk_score"] < 60 else "🔴")
        reasons_text = "\n".join([f"• {r}" for r in report["reasons"]]) if report["reasons"] else "• ពុំមានសញ្ញាហានិភ័យបច្ចេកទេសត្រូវបានរកឃើញឡើយ"

        msg = (
            f"🛡️ *[លទ្ធផលស្កេនសុវត្ថិភាពឌីជីថល]* ✨\n\n"
            f"📊 *ស្ថានភាព៖* {report['status_label']}\n"
            f"🎯 *ពិន្ទុហានិភ័យ (Risk Score)៖* {score_bar} `{report['risk_score']} / 100`\n"
            f"🌐 *Domain/Target:* `{report['domain']}`\n\n"
            f"🔍 *កត្តាហានិភ័យដែលបានរកឃើញ៖*\n{reasons_text}\n\n"
            f"🧠 *ការវាយតម្លៃរបស់ AI៖*\n_{report['ai_verdict']}_\n\n"
            f"💡 *អនុសាសន៍ការពារ៖*\n{report['advice']}\n\n"
            f"📌 *ចំណាំបន្ថែម៖* {report['safety_tip']}"
        )

        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu ដើម", callback_data="btn_back_main")]])
        await safe_edit_text(status_msg, msg, reply_markup=kb)

    except Exception as e:
        logger.error(f"Error in scan_command: {e}")
        await safe_edit_text(status_msg, f"❌ កំហុសក្នុងការស្កេន៖ {str(e)[:120]}")

async def tempmail_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Manage 10-minute temporary disposable email for receiving verification OTPs: /tempmail or /mail."""
    chat = update.effective_chat
    await update.message.chat.send_action("typing")

    try:
        from services.temp_mail_service import get_current_email, generate_temp_email, check_inbox
        email = get_current_email(chat.id)
        if not email:
            email = await generate_temp_email(chat.id)

        success, curr_email, messages = await check_inbox(chat.id)

        kb_rows = [
            [
                InlineKeyboardButton("🔄 ពិនិត្យសារថ្មី (Check Inbox)", callback_data="mail_refresh"),
                InlineKeyboardButton("🆕 បង្កើត Email ថ្មី", callback_data="mail_new"),
            ]
        ]

        if messages:
            mail_list_text = "📬 *សារដែលបានទទួលក្នុង Inbox៖*\n\n"
            for idx, m in enumerate(messages[:5], 1):
                sender = m.get("from", "Unknown")[:25]
                subject = m.get("subject", "No subject")[:30]
                mid = m.get("id")
                mail_list_text += f"{idx}. 📩 *ពី:* `{sender}`\n   📌 *កម្មវត្ថុ:* {subject}\n\n"
                kb_rows.append([InlineKeyboardButton(f"📖 អានសារ #{idx}: {subject[:20]}", callback_data=f"mail_read_{mid}")])
        else:
            mail_list_text = "📭 *Inbox ទំនេរ (មិនទាន់មានសារថ្មីនៅឡើយទេ)*\n_នៅពេលមានគេផ្ញើអ៊ីមែល ឬកូដ OTP មក វានឹងបង្ហាញនៅទីនេះភ្លាមៗ!_"

        text = (
            "📧 *[10-Minute Disposable Email - អ៊ីមែលបណ្តោះអាសន្ន]* 🛡️\n\n"
            f"📬 *អាសយដ្ឋាន Email របស់អ្នក៖*\n`{curr_email}`\n\n"
            "💡 _ចុចលើ Email ខាងលើដើម្បី Copy យកទៅចុះឈ្មោះ ឬទទួលកូដ OTP ដោយមិនបារម្ភរឿង Spam ក្នុង Email ពិតប្រាកដ!_\n\n"
            f"{mail_list_text}"
        )
        kb_rows.append([InlineKeyboardButton("🔙 Menu ដើម", callback_data="btn_back_main")])
        await safe_reply_text(update.message, text, reply_markup=InlineKeyboardMarkup(kb_rows))

    except Exception as e:
        logger.error(f"Error in tempmail_command: {e}")
        await safe_reply_text(update.message, f"❌ កំហុសបច្ចេកទេសក្នុងសេវាអ៊ីមែល៖ {str(e)[:120]}")

async def web_builder_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generate instant modern responsive landing page website in 30 seconds: /web, /page, /site."""
    chat = update.effective_chat
    user_text = " ".join(context.args) if context.args else ""
    if not user_text and update.message and update.message.reply_to_message:
        user_text = update.message.reply_to_message.text or update.message.reply_to_message.caption or ""

    if not user_text:
        tip = (
            "🌐 *[Instant Mini Landing Page Builder - បង្កើត Web ផ្ទាល់ខ្លួន 30s]* ✨\n\n"
            "គ្រាន់តែប្រាប់ Bot ពីអាជីវកម្ម ឬជំនាញរបស់អ្នក ➔ AI នឹងរចនាគេហទំព័រ Landing Page ដ៏ទំនើបមួយភ្លាមៗ "
            "ដែលបើកមើលបានលើ Telegram Mini App ព្រមទាំងទាញយក File កូដ HTML ទៅ Host លើ Domain ផ្ទាល់ខ្លួនបាន!\n\n"
            "👉 *របៀបប្រើប្រាស់៖*\n"
            "វាយ៖ `/web <ព័ត៌មានដែលចង់បាន>` ឬ `/page <ព័ត៌មាន>`\n\n"
            "• ឧទាហរណ៍៖ `/web ខ្ញុំជាអ្នកថតរូបឈ្មោះ សុខា ចង់បានគេហទំព័រដាក់រូបថត សេវាកម្ម និងលេខទូរស័ព្ទ 012888999 @sokha_photo`\n"
            "• ឧទាហរណ៍៖ `/web ហាងកាហ្វេ Cafe Amazon សាខាទួលគោក មានម៉ឺនុយភេសជ្ជៈ ប្រូម៉ូសិន និងផែនទី`\n"
            "• ឧទាហរណ៍៖ `/web អ្នកលក់ឡេ Online សេវាដឹក ២៥ ខេត្តក្រុង មានប៊ូតុងឆាត Telegram និង Facebook`\n"
            "• ឧទាហរណ៍៖ `/web Portfolio អ្នកសរសេរកូដ Full-Stack Developer ជំនាញ Python & React`\n\n"
            "👇 _ឬចុចជ្រើសរើសគំរូរហ័ស (Quick Presets) ខាងក្រោមដើម្បីសាកល្បង៖_"
        )
        kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("📸 គំរូអ្នកថតរូប", callback_data="web_preset_photo"),
                InlineKeyboardButton("☕ គំរូហាងកាហ្វេ", callback_data="web_preset_cafe"),
            ],
            [
                InlineKeyboardButton("💄 គំរូលក់ទំនិញ", callback_data="web_preset_shop"),
                InlineKeyboardButton("💻 គំរូ Portfolio IT", callback_data="web_preset_dev"),
            ],
            [InlineKeyboardButton("🔙 Menu ដើម", callback_data="btn_back_main")]
        ])
        await safe_reply_text(update.message, tip, reply_markup=kb)
        return

    status_msg = await update.message.reply_text("🌐 *AI កំពុងរចនា និងបង្កើតគេហទំព័រ Landing Page ដ៏ទំនើបរបស់អ្នក...* ⏳\nសូមរង់ចាំប្រហែល ១០ វិនាទី! 🚀", parse_mode="Markdown")
    await update.message.chat.send_action("upload_document")

    try:
        from services.web_builder_service import generate_landing_page
        import io
        ok, site_id, site_url, html_str, summary = await generate_landing_page(user_text, chat.id)
        if not ok:
            await safe_edit_text(status_msg, f"❌ {summary}")
            return

        buttons = [
            [InlineKeyboardButton("🌐 បើកមើល Website លើទូរស័ព្ទ (Mini App)", web_app=WebAppInfo(url=site_url))],
            [InlineKeyboardButton("🔗 បើកមើលលើ Browser / Safari", url=site_url)],
            [InlineKeyboardButton("🔙 Menu ដើម", callback_data="btn_back_main")]
        ]

        card_text = (
            "🎉 *[បានបង្កើតគេហទំព័រ Landing Page ជោគជ័យ!]* 🌐✨\n\n"
            f"{summary}\n\n"
            "💡 *លក្ខណៈពិសេស៖*\n"
            "• រចនាបថ Glassmorphism Dark Mode ទំនើបកម្រិតអន្តរជាតិ\n"
            "• បង្ហាញរូបភាពច្បាស់ HD និងសេវាកម្មច្បាស់ៗ\n"
            "• ប៊ូតុង Call ភ្លាមៗ និង Chat Telegram ផ្ទាល់\n"
            "• ដំណើរការរលូនលើទូរស័ព្ទដៃ iPhone និង Android\n\n"
            "👇 _ចុចប៊ូតុងខាងក្រោមដើម្បីបើកមើលភ្លាមៗ ឬទាញយកឯកសារកូដ HTML ខាងក្រោម៖_"
        )
        await safe_edit_text(status_msg, card_text, reply_markup=InlineKeyboardMarkup(buttons))

        html_file = io.BytesIO(html_str.encode("utf-8"))
        html_file.name = f"{site_id}.html"
        await update.message.reply_document(
            document=html_file,
            filename=f"{site_id}.html",
            caption=f"📎 *ឯកសារកូដ Website ពេញលេញ (.html)*\n_លោកអ្នកអាចទាញយក File នេះយកទៅ Host លើ Domain ផ្ទាល់ខ្លួន (Netlify, Vercel, GitHub) បានយ៉ាងងាយស្រួល!_",
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Error in web_builder_command: {e}")
        await safe_edit_text(status_msg, f"❌ កំហុសបច្ចេកទេសក្នុងការបង្កើត Website៖ {str(e)[:120]}")


