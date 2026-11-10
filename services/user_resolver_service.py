import re
import logging
from typing import Dict, Any, Optional, Tuple, List
from telegram import InlineKeyboardMarkup, InlineKeyboardButton
from database import find_users_in_db

logger = logging.getLogger(__name__)

def extract_telegram_username(raw_text: str) -> Optional[str]:
    """
    Extract clean Telegram username from various formats:
    - heamlyheak
    - @heamlyheak
    - https://t.me/heamlyheak
    - t.me/heamlyheak
    - tg://resolve?domain=heamlyheak
    """
    if not raw_text:
        return None
    raw = raw_text.strip()
    
    # Check if URL format
    m_url = re.search(r'(?:https?:\/\/)?(?:www\.)?t\.me\/([a-zA-Z0-9_]{3,32})', raw, re.IGNORECASE)
    if m_url:
        return m_url.group(1)
        
    m_tg = re.search(r'tg:\/\/resolve\?domain=([a-zA-Z0-9_]{3,32})', raw, re.IGNORECASE)
    if m_tg:
        return m_tg.group(1)
        
    # Check if @username or plain username
    clean = raw.lstrip("@").strip()
    if re.match(r'^[a-zA-Z0-9_]{3,32}$', clean):
        return clean
        
    return None

def validate_username_format(raw_text: str) -> Tuple[bool, str, str]:
    """
    Validate username format.
    Returns: (is_valid, clean_username, error_message_km)
    """
    if not raw_text or not raw_text.strip():
        return (
            False,
            "",
            "💡 *របៀបប្រើប្រាស់ Telegram Profile Resolver៖*\n\n"
            "សូមវាយពាក្យបញ្ជា៖ `/user <username>` ឬ `/whois <username>`\n\n"
            "• ឧទាហរណ៍៖ `/user heamlyheak`\n"
            "• ឧទាហរណ៍៖ `/whois @heamlyheak`\n"
            "• ឧទាហរណ៍៖ `/user https://t.me/heamlyheak`\n\n"
            "Bot នឹងផ្ទៀងផ្ទាត់ និងបង្កើតប៊ូតុងផ្លូវកាត់ (1-Click Chat & Profile) ជូនភ្លាមៗ! 🚀"
        )
        
    clean = extract_telegram_username(raw_text)
    if not clean:
        return (
            False,
            "",
            "⚠️ *ទម្រង់ Username មិនត្រឹមត្រូវឡើយ!*\n\n"
            "• Telegram Username ត្រូវមានប្រវែងពី ៣ ទៅ ៣២ តួអក្សរ\n"
            "• អាចប្រើប្រាស់បានតែតួអក្សរអង់គ្លេស (a-z, A-Z), លេខ (0-9), និងសញ្ញា underscore (`_`)\n"
            "• ឧទាហរណ៍ត្រឹមត្រូវ៖ `/user heamlyheak`"
        )
        
    return True, clean, ""

async def resolve_telegram_user(bot, raw_query: str) -> Dict[str, Any]:
    """
    Resolve Telegram username, check internal database, and attempt public profile lookup.
    """
    is_valid, clean_user, err_msg = validate_username_format(raw_query)
    if not is_valid:
        return {
            "valid": False,
            "error_msg": err_msg,
            "username": "",
        }

    url_https = f"https://t.me/{clean_user}"
    url_tg = f"tg://resolve?domain={clean_user}"
    
    # 1. Search local bot database
    db_matches = find_users_in_db(clean_user)
    in_db = len(db_matches) > 0
    db_record = db_matches[0] if in_db else None

    result: Dict[str, Any] = {
        "valid": True,
        "username": clean_user,
        "url_https": url_https,
        "url_tg": url_tg,
        "in_database": in_db,
        "db_record": db_record,
        "verified_via_api": False,
        "chat_type": "user",
        "type_km": "គណនី Telegram (Personal User)",
        "display_name": clean_user,
        "chat_id": db_record["chat_id"] if db_record else None,
        "bio": "",
    }

    # 2. Attempt get_chat via Telegram Bot API if bot is available
    if bot:
        try:
            chat = await bot.get_chat(f"@{clean_user}")
            result["verified_via_api"] = True
            result["chat_id"] = chat.id
            
            c_type = getattr(chat, "type", "private")
            if c_type == "channel":
                result["chat_type"] = "channel"
                result["type_km"] = "ប៉ុស្តិ៍ផ្សាយផ្លូវការ (Public Channel) 📢"
            elif c_type in ["group", "supergroup"]:
                result["chat_type"] = "group"
                result["type_km"] = "ក្រុមសាធារណៈ (Public Group) 👥"
            elif getattr(chat, "is_bot", False) or clean_user.lower().endswith("bot"):
                result["chat_type"] = "bot"
                result["type_km"] = "Telegram Bot 🤖"
            else:
                result["chat_type"] = "user"
                result["type_km"] = "គណនីផ្ទាល់ខ្លួន (Personal Account) 👤"

            name_parts = []
            if getattr(chat, "first_name", None):
                name_parts.append(chat.first_name)
            if getattr(chat, "last_name", None):
                name_parts.append(chat.last_name)
            if getattr(chat, "title", None):
                name_parts.append(chat.title)
            
            if name_parts:
                result["display_name"] = " ".join(name_parts)
                
            bio = getattr(chat, "bio", "") or getattr(chat, "description", "")
            if bio:
                result["bio"] = bio
        except Exception as e:
            # Expected for private accounts not in chat with bot
            logger.debug(f"get_chat for @{clean_user} exception (normal for private users): {e}")

    return result

def format_user_resolver_card(data: Dict[str, Any]) -> Tuple[str, InlineKeyboardMarkup]:
    """
    Format elegant Telegram profile resolution report card and 1-Click buttons.
    """
    if not data.get("valid"):
        return data.get("error_msg", "កំហុសមិនស្គាល់"), InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Menu ដើម", callback_data="btn_back_main")]
        ])

    username = data["username"]
    url_https = data["url_https"]
    type_km = data.get("type_km", "គណនី Telegram")
    display_name = data.get("display_name", username)
    chat_id = data.get("chat_id")
    bio = data.get("bio", "")
    in_db = data.get("in_database", False)

    db_status = "✅ ធ្លាប់មានវត្តមានក្នុងប្រព័ន្ធ Bot" if in_db else "🌐 គណនីខាងក្រៅ (Telegram Global Profile)"

    lines = [
        "👤 *លទ្ធផលស្វែងរក & ផ្ទៀងផ្ទាត់គណនី Telegram* ✨",
        "━━━━━━━━━━━━━━━━━━━━━━",
        f"• *Username:* `@{username}`",
        f"• *ប្រភេទគណនី:* {type_km}",
    ]

    if display_name and display_name != username:
        lines.append(f"• *ឈ្មោះសម្គាល់:* *{display_name}*")

    if chat_id:
        lines.append(f"• *Telegram ID:* `{chat_id}`")

    if bio:
        lines.append(f"• *Bio / ពិពណ៌នា:* _{bio[:120]}_")

    lines.append(f"• *ស្ថានភាពទិន្នន័យ:* {db_status}")
    lines.append("")
    lines.append("🔗 *តំណភ្ជាប់ផ្លូវការ (Direct Shortcuts)៖*")
    lines.append(f"👉 **Web Link:** [t.me/{username}]({url_https})")
    lines.append(f"👉 **App Deep Link:** `tg://resolve?domain={username}`")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━")
    lines.append("💡 _ចុចប៊ូតុងខាងក្រោមដើម្បី **បើកផ្ញើសារ (Chat Now)** ទៅកាន់គណនីនេះភ្លាមៗមួយចុច (1-Click)!_")

    card_text = "\n".join(lines)

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("💬 បើកផ្ញើសារ (Chat 1-Click)", url=url_https),
        ],
        [
            InlineKeyboardButton("🌐 បើកលើ Browser / Web", url=url_https),
            InlineKeyboardButton("🔙 Menu ដើម", callback_data="btn_back_main")
        ]
    ])

    return card_text, keyboard
