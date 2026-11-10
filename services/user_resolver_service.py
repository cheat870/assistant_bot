import re
import logging
import asyncio
from typing import Dict, Any, Optional, Tuple, List
import httpx
from telegram import InlineKeyboardMarkup, InlineKeyboardButton
from database import find_users_in_db

logger = logging.getLogger(__name__)

HTTP_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

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
            "• ឧទាហរណ៍៖ `/whois @lyheak`\n"
            "• ឧទាហរណ៍៖ `/user https://t.me/durov`\n\n"
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

async def check_telegram_public_web(client: httpx.AsyncClient, username: str) -> Dict[str, Any]:
    """Check if a username actually exists publicly on Telegram's web gateway."""
    try:
        resp = await client.get(f"https://t.me/{username}")
        if resp.status_code != 200:
            return {"exists": False, "username": username}
            
        html = resp.text
        has_title = 'tgme_page_title' in html
        has_photo = 'tgme_page_photo' in html
        exists = has_title or has_photo
        
        title, extra, bio = "", "", ""
        if exists:
            mt = re.search(r'class="tgme_page_title"[^>]*>(.*?)</div>', html, re.DOTALL)
            if mt:
                title = re.sub(r'<[^>]+>', '', mt.group(1)).strip()
            me = re.search(r'class="tgme_page_extra"[^>]*>(.*?)</div>', html, re.DOTALL)
            if me:
                extra = re.sub(r'<[^>]+>', '', me.group(1)).strip()
            md = re.search(r'class="tgme_page_description"[^>]*>(.*?)</div>', html, re.DOTALL)
            if md:
                bio = re.sub(r'<[^>]+>', '', md.group(1)).strip()
                
        return {
            "exists": exists,
            "username": username,
            "title": title,
            "extra": extra,
            "bio": bio,
        }
    except Exception as e:
        logger.debug(f"Web check error for @{username}: {e}")
        return {"exists": False, "username": username}

async def resolve_telegram_user(bot, raw_query: str) -> Dict[str, Any]:
    """
    Resolve Telegram username, verify if it truly exists on Telegram,
    check internal database, and perform smart fuzzy search.
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

    # 2. Real-time Web Verification via t.me gateway
    async with httpx.AsyncClient(timeout=5.0, headers=HTTP_HEADERS, follow_redirects=True) as client:
        web_info = await check_telegram_public_web(client, clean_user)
        
        exists_on_telegram = web_info.get("exists", False)
        display_name = web_info.get("title", "")
        extra_info = web_info.get("extra", "")
        bio = web_info.get("bio", "")

        # 3. If bot instance available, also try get_chat API
        verified_via_bot = False
        chat_type = "user"
        type_km = "គណនីផ្ទាល់ខ្លួន (Personal Account) 👤"
        chat_id = db_record["chat_id"] if db_record else None

        if bot:
            try:
                chat = await bot.get_chat(f"@{clean_user}")
                exists_on_telegram = True
                verified_via_bot = True
                chat_id = chat.id
                
                c_type = getattr(chat, "type", "private")
                if c_type == "channel":
                    chat_type = "channel"
                    type_km = "ប៉ុស្តិ៍ផ្សាយផ្លូវការ (Public Channel) 📢"
                elif c_type in ["group", "supergroup"]:
                    chat_type = "group"
                    type_km = "ក្រុមសាធារណៈ (Public Group) 👥"
                elif getattr(chat, "is_bot", False) or clean_user.lower().endswith("bot"):
                    chat_type = "bot"
                    type_km = "Telegram Bot 🤖"
                else:
                    chat_type = "user"
                    type_km = "គណនីផ្ទាល់ខ្លួន (Personal Account) 👤"

                name_parts = []
                if getattr(chat, "first_name", None):
                    name_parts.append(chat.first_name)
                if getattr(chat, "last_name", None):
                    name_parts.append(chat.last_name)
                if getattr(chat, "title", None):
                    name_parts.append(chat.title)
                
                if name_parts and not display_name:
                    display_name = " ".join(name_parts)
                    
                b = getattr(chat, "bio", "") or getattr(chat, "description", "")
                if b and not bio:
                    bio = b
            except Exception:
                pass

        # 4. If account doesn't exist, check 2-3 potential variations (e.g. suffixes or parts)
        similar_match = None
        if not exists_on_telegram and not in_db:
            candidates = []
            # If user has multiple words/parts like heamlyheak -> check lyheak, heam_lyheak
            if len(clean_user) > 6:
                candidates.append(clean_user[4:])  # e.g. lyheak from heamlyheak
                candidates.append(f"{clean_user[:4]}_{clean_user[4:]}")  # e.g. heam_lyheak
            
            for c in candidates:
                if len(c) >= 4:
                    c_info = await check_telegram_public_web(client, c)
                    if c_info.get("exists"):
                        similar_match = c_info
                        break

    return {
        "valid": True,
        "username": clean_user,
        "exists_on_telegram": exists_on_telegram or in_db or verified_via_bot,
        "url_https": url_https,
        "url_tg": url_tg,
        "in_database": in_db,
        "db_record": db_record,
        "chat_type": chat_type,
        "type_km": type_km,
        "display_name": display_name,
        "extra_info": extra_info,
        "chat_id": chat_id,
        "bio": bio,
        "similar_match": similar_match,
    }

def format_user_resolver_card(data: Dict[str, Any]) -> Tuple[str, InlineKeyboardMarkup]:
    """
    Format elegant Telegram profile resolution report card and 1-Click buttons.
    """
    if not data.get("valid"):
        return data.get("error_msg", "កំហុសមិនស្គាល់"), InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Menu ដើម", callback_data="btn_back_main")]
        ])

    username = data["username"]
    exists = data.get("exists_on_telegram", False)
    url_https = data["url_https"]
    type_km = data.get("type_km", "គណនីផ្ទាល់ខ្លួន (Personal Account) 👤")
    display_name = data.get("display_name", "")
    extra_info = data.get("extra_info", "")
    chat_id = data.get("chat_id")
    bio = data.get("bio", "")
    in_db = data.get("in_database", False)
    similar = data.get("similar_match")

    # CASE 1: Account NOT found on Telegram
    if not exists:
        lines = [
            f"❌ *រកមិនឃើញ Username @{username} លើ Telegram ឡើយ!* (Not Found)",
            "━━━━━━━━━━━━━━━━━━━━━━",
            f"⚠️ Telegram បានបញ្ជាក់ថា ពុំមានគណនីណាបានចុះឈ្មោះប្រើប្រាស់ Username `@{username}` នេះនៅឡើយទេ។",
            "",
            "🧐 *មូលហេតុចម្បងដែលរកមិនឃើញ៖*",
            f"១. **ឈ្មោះ \"{username}\" គ្រាន់តែជា Display Name មិនមែនជា @Username ឡើយ៖**",
            "   • នៅក្នុង Telegram មនុស្សភាគច្រើនកំណត់តែ Display Name (ឈ្មោះបង្ហាញផ្ទាល់ខ្លួន ឧ. Heam Lyheak) ប៉ុន្តែ**ពុំទាន់បានបង្កើត @Username** នៅក្នុង Settings របស់ខ្លួននៅឡើយទេ។",
            "   • ប្រសិនបើគាត់ពុំទាន់បានកំណត់ @Username ទេ នោះប្រព័ន្ធមិនអាចបើក Chat តាម Link បានឡើយ។",
            "២. **សរសេរខុសអក្ខរាវិរុទ្ធ (Typo / Spelling)៖**",
            "   • ប្រហែលជាគណនីនោះប្រើ Username ផ្សេង (ឧ. មានសញ្ញា `_` ឬលេខបន្ថែម)។",
        ]

        buttons = []
        if similar:
            s_user = similar["username"]
            s_title = similar.get("title", s_user)
            lines.append("")
            lines.append(f"💡 *បានរកឃើញគណនីស្រដៀងគ្នានេះ៖* `@{s_user}` (*{s_title}*)")
            buttons.append([InlineKeyboardButton(f"👉 ពិនិត្យមើល @{s_user} ({s_title[:15]})", url=f"https://t.me/{s_user}")])

        lines.append("")
        lines.append("🔍 *វិធីស្វែងរកមនុស្សតាមឈ្មោះ (Display Name) ក្នុង Telegram App៖*")
        lines.append(f"👉 សូមចុចលើ **ប្រអប់ស្វែងរក (🔍 Search)** ខាងលើបង្អស់ក្នុង Telegram App")
        lines.append(f"👉 វាយពាក្យ *\"{username}\"* នោះ Telegram នឹងស្វែងរកទាំងក្នុង Contacts, Global Users, Groups និង Channels ជូនភ្លាមៗ!")

        buttons.append([InlineKeyboardButton("🔙 Menu ដើម", callback_data="btn_back_main")])
        return "\n".join(lines), InlineKeyboardMarkup(buttons)

    # CASE 2: Account EXISTS and is Verified!
    db_status = "✅ ធ្លាប់មានវត្តមានក្នុងប្រព័ន្ធ Bot" if in_db else "🌐 គណនី Telegram សាធារណៈ"

    lines = [
        "✅ *បានផ្ទៀងផ្ទាត់៖ រកឃើញគណនីលើ Telegram!* ✨",
        "━━━━━━━━━━━━━━━━━━━━━━",
        f"• *Telegram Username:* `@{username}`",
    ]

    if display_name:
        lines.append(f"• *ឈ្មោះបង្ហាញ (Display Name):* *{display_name}*")

    lines.append(f"• *ប្រភេទគណនី:* {type_km}")

    if extra_info and extra_info != f"@{username}":
        lines.append(f"• *ចំនួនសមាជិក/ព័ត៌មាន:* `{extra_info}`")

    if chat_id:
        lines.append(f"• *Telegram ID:* `{chat_id}`")

    if bio:
        lines.append(f"• *Bio / ពិពណ៌នា:* _{bio[:150]}_")

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
