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
    Extract clean Telegram query or username from input:
    - heamlyheak
    - @heamlyheak
    - heam lyheak
    - https://t.me/heamlyheak
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
        
    # Remove @ prefix
    clean = raw.lstrip("@").strip()
    return clean if clean else None

def validate_username_format(raw_text: str) -> Tuple[bool, str, str]:
    """
    Validate search query format.
    Returns: (is_valid, clean_query, error_message_km)
    """
    if not raw_text or not raw_text.strip():
        return (
            False,
            "",
            "💡 *របៀបស្វែងរកគណនី Telegram (Search User & Profile Resolver)៖*\n\n"
            "សូមវាយពាក្យបញ្ជា៖ `/user <ឈ្មោះ ឬ username>` ឬ `/whois <ឈ្មោះ>`\n\n"
            "• ឧទាហរណ៍៖ `/user heamlyheak`\n"
            "• ឧទាហរណ៍៖ `/user heam lyheak`\n"
            "• ឧទាហរណ៍៖ `/whois @lyheak`\n"
            "• ឧទាហរណ៍៖ `/user socheat`\n\n"
            "Bot នឹងស្វែងរក និងបង្ហាញគណនីទាំងអស់ដែលមានឈ្មោះដូច ឬស្រដៀងគ្នា ព្រមទាំងផ្ដល់ប៊ូតុង Chat 1-Click ជូនភ្លាមៗ! 🚀"
        )
        
    clean = extract_telegram_username(raw_text)
    if not clean or len(clean) < 2:
        return (
            False,
            "",
            "⚠️ *សូមវាយឈ្មោះយ៉ាងហោចណាស់ ២ តួអក្សរឡើងទៅ!* ឧទាហរណ៍៖ `/user heamlyheak`"
        )
        
    return True, clean, ""

def generate_smart_candidates(raw_query: str) -> List[str]:
    """Generate smart plausible Telegram username variants from query."""
    raw_clean = re.sub(r'https?://(?:www\.)?t\.me/', '', raw_query).lstrip('@').strip()
    words = [w.lower() for w in re.split(r'[\s_.-]+', raw_clean) if len(w) >= 2]
    candidates = []
    
    # 1. Direct joined
    joined = ''.join(words)
    if 3 <= len(joined) <= 32:
        candidates.append(joined)
        
    # 2. Multi-word permutations
    if len(words) > 1:
        u_joined = '_'.join(words)
        if 3 <= len(u_joined) <= 32:
            candidates.append(u_joined)
        rev_joined = '_'.join(reversed(words))
        if 3 <= len(rev_joined) <= 32:
            candidates.append(rev_joined)
            
    # 3. Individual words
    for w in words:
        if 3 <= len(w) <= 32:
            candidates.append(w)
            
    # 4. If single long word, generate logical splits (e.g. heamlyheak -> lyheak, heam, heam_lyheak)
    if len(words) == 1 and len(joined) >= 6:
        for i in range(3, min(7, len(joined) - 2)):
            left, right = joined[:i], joined[i:]
            if len(left) >= 3:
                candidates.append(left)
            if len(right) >= 3:
                candidates.append(right)
            if len(left) >= 3 and len(right) >= 3:
                candidates.append(f"{left}_{right}")
                candidates.append(f"{right}_{left}")
                
    # 5. Affixes for top bases
    top_bases = list(candidates)[:4]
    for b in top_bases:
        candidates.append(f"{b}_kh")
        candidates.append(f"{b}kh")
        candidates.append(f"{b}_official")
        candidates.append(f"{b}1")
        candidates.append(f"{b}_bot")

    seen = set()
    final = []
    for c in candidates:
        c_clean = re.sub(r'[^a-zA-Z0-9_]', '', c.lower())
        if c_clean not in seen and 3 <= len(c_clean) <= 32:
            seen.add(c_clean)
            final.append(c_clean)
            
    return final[:18]

async def check_telegram_public_web(client: httpx.AsyncClient, username: str) -> Optional[Dict[str, Any]]:
    """Check if a username actually exists publicly on Telegram's web gateway."""
    try:
        resp = await client.get(f"https://t.me/{username}")
        if resp.status_code != 200:
            return None
            
        html = resp.text
        has_title = 'tgme_page_title' in html
        has_photo = 'tgme_page_photo' in html
        if not (has_title or has_photo):
            return None
            
        title, extra, bio = "", "", ""
        mt = re.search(r'class="tgme_page_title"[^>]*>(.*?)</div>', html, re.DOTALL)
        if mt:
            title = re.sub(r'<[^>]+>', '', mt.group(1)).strip()
        me = re.search(r'class="tgme_page_extra"[^>]*>(.*?)</div>', html, re.DOTALL)
        if me:
            extra = re.sub(r'<[^>]+>', '', me.group(1)).strip()
        md = re.search(r'class="tgme_page_description"[^>]*>(.*?)</div>', html, re.DOTALL)
        if md:
            bio = re.sub(r'<[^>]+>', '', md.group(1)).strip()

        # Deduce account type
        type_km = "គណនីផ្ទាល់ខ្លួន 👤"
        if "subscribers" in extra.lower() or "channel" in html.lower():
            type_km = "ប៉ុស្តិ៍ Channel 📢"
        elif "members" in extra.lower() or "group" in html.lower():
            type_km = "ក្រុម Group 👥"
        elif username.lower().endswith("bot") or "bot" in extra.lower():
            type_km = "Telegram Bot 🤖"
            
        return {
            "username": username,
            "title": title or username,
            "extra": extra,
            "bio": bio,
            "type_km": type_km,
            "url_https": f"https://t.me/{username}",
            "url_tg": f"tg://resolve?domain={username}",
        }
    except Exception as e:
        logger.debug(f"Web check error for @{username}: {e}")
        return None

async def resolve_telegram_user(bot, raw_query: str) -> Dict[str, Any]:
    """
    Search and resolve Telegram users: checks exact query, tests smart variations,
    and returns all active matching profiles found across Telegram and local DB.
    """
    is_valid, clean_query, err_msg = validate_username_format(raw_query)
    if not is_valid:
        return {
            "valid": False,
            "error_msg": err_msg,
            "query": raw_query,
            "matches": [],
        }

    # Generate search candidates
    candidates = generate_smart_candidates(clean_query)
    
    # 1. Real-time batch check across Telegram's gateway
    async with httpx.AsyncClient(timeout=4.5, headers=HTTP_HEADERS, follow_redirects=True) as client:
        results = await asyncio.gather(*[check_telegram_public_web(client, c) for c in candidates])
        
    found_map: Dict[str, Dict[str, Any]] = {}
    for r in results:
        if r and r["username"] not in found_map:
            found_map[r["username"]] = r

    # 2. Check local database for matching records
    db_matches = find_users_in_db(clean_query)
    for db_user in db_matches:
        u_name = db_user.get("username")
        if u_name and u_name.lower() not in found_map:
            found_map[u_name.lower()] = {
                "username": u_name,
                "title": f"សមាជិក ID: {db_user.get('chat_id')}",
                "extra": "ក្នុងប្រព័ន្ធ Bot",
                "bio": "",
                "type_km": "គណនីក្នុងប្រព័ន្ធ Bot 💾",
                "url_https": f"https://t.me/{u_name}",
                "url_tg": f"tg://resolve?domain={u_name}",
            }

    # 3. If bot is available and primary query not yet found, try get_chat
    clean_single = re.sub(r'[^a-zA-Z0-9_]', '', clean_query.lower())
    if bot and clean_single and clean_single not in found_map:
        try:
            chat = await bot.get_chat(f"@{clean_single}")
            c_type = getattr(chat, "type", "private")
            type_km = "គណនីផ្ទាល់ខ្លួន 👤"
            if c_type == "channel":
                type_km = "ប៉ុស្តិ៍ Channel 📢"
            elif c_type in ["group", "supergroup"]:
                type_km = "ក្រុម Group 👥"
            elif getattr(chat, "is_bot", False) or clean_single.endswith("bot"):
                type_km = "Telegram Bot 🤖"
                
            name_parts = [p for p in [getattr(chat, "first_name", ""), getattr(chat, "last_name", ""), getattr(chat, "title", "")] if p]
            display_title = " ".join(name_parts) if name_parts else clean_single
            bio = getattr(chat, "bio", "") or getattr(chat, "description", "")
            
            found_map[clean_single] = {
                "username": clean_single,
                "title": display_title,
                "extra": f"@{clean_single}",
                "bio": bio,
                "type_km": type_km,
                "url_https": f"https://t.me/{clean_single}",
                "url_tg": f"tg://resolve?domain={clean_single}",
            }
        except Exception:
            pass

    matches_list = list(found_map.values())
    exact_match = found_map.get(clean_single)

    return {
        "valid": True,
        "query": clean_query,
        "clean_single": clean_single,
        "exact_match": exact_match,
        "matches": matches_list,
    }

def format_user_resolver_card(data: Dict[str, Any]) -> Tuple[str, InlineKeyboardMarkup]:
    """
    Format report card displaying ALL matching and similar Telegram profiles found.
    """
    if not data.get("valid"):
        return data.get("error_msg", "កំហុសមិនស្គាល់"), InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Menu ដើម", callback_data="btn_back_main")]
        ])

    query = data.get("query", "")
    exact = data.get("exact_match")
    matches = data.get("matches", [])
    clean_single = data.get("clean_single", "")

    # CASE 1: No matches found at all
    if not matches:
        lines = [
            f"❌ *រកមិនឃើញគណនី ឬ Username ណាដែលស្រដៀងនឹង \"{query}\" ឡើយ!*",
            "━━━━━━━━━━━━━━━━━━━━━━",
            f"⚠️ Telegram ពុំទាន់មានគណនីណាបានចុះឈ្មោះប្រើ Username ឬពាក្យសម្គាល់នេះនៅឡើយទេ។",
            "",
            "🧐 *មូលហេតុចម្បង៖*",
            f"១. **ឈ្មោះ \"{query}\" អាចជា Display Name (ឈ្មោះបង្ហាញ) មិនមែនជា @Username ឡើយ៖**",
            "   • អ្នកប្រើប្រាស់ភាគច្រើនកំណត់តែឈ្មោះ Profile ផ្ទាល់ខ្លួន ប៉ុន្តែ**ពុំទាន់បានកំណត់ @Username** នៅក្នុង Settings របស់ខ្លួននៅឡើយទេ។",
            "២. **សរសេរខុសអក្ខរាវិរុទ្ធ (Typo/Spelling)៖**",
            "   • សូមពិនិត្យមើលអក្សរឡើងវិញ ឬសាកល្បងឈ្មោះផ្សេង។",
            "",
            "🔍 *វិធីស្វែងរកមនុស្សតាមឈ្មោះ (Display Name) ក្នុង Telegram App៖*",
            f"👉 សូមចុចលើ **ប្រអប់ស្វែងរក (🔍 Search)** ខាងលើបង្អស់ក្នុង Telegram App របស់អ្នក",
            f"👉 វាយពាក្យ *\"{query}\"* នោះ Telegram នឹងស្វែងរកទាំងក្នុង Contacts, Global Users, Groups និង Channels ជូនភ្លាមៗ!",
        ]
        return "\n".join(lines), InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu ដើម", callback_data="btn_back_main")]])

    buttons = []
    lines = [
        f"🔍 *លទ្ធផលស្វែងរកគណនី Telegram ទាំងអស់ដែលស្រដៀងនឹង \"{query}\"* ✨",
        "━━━━━━━━━━━━━━━━━━━━━━",
    ]

    # If exact match exists, highlight it at the top
    if exact:
        lines.append("🎯 *គណនីត្រូវគ្នា ១០០% (Exact Match)៖*")
        lines.append(f"• *Username:* `@{exact['username']}`")
        lines.append(f"• *ឈ្មោះបង្ហាញ (Name):* *{exact['title']}*")
        lines.append(f"• *ប្រភេទគណនី:* {exact['type_km']}")
        if exact.get("extra") and exact["extra"] != f"@{exact['username']}":
            lines.append(f"• *ព័ត៌មានបន្ថែម:* `{exact['extra']}`")
        if exact.get("bio"):
            lines.append(f"• *Bio / ពិពណ៌នា:* _{exact['bio'][:120]}_")
        lines.append(f"👉 [ចុចបើក Chat (t.me/{exact['username']})]({exact['url_https']})")
        lines.append("")

    # List all similar matches
    other_matches = [m for m in matches if not (exact and m["username"] == exact["username"])]
    if other_matches:
        count_label = f" ({len(other_matches)})" if len(other_matches) > 1 else ""
        if exact:
            lines.append(f"👥 *គណនីស្រដៀងគ្នាផ្សេងទៀតដែលបានរកឃើញ{count_label}៖*")
        else:
            lines.append(f"⚠️ *មិនមាន Username ជាក់លាក់ `@{clean_single}` ឡើយ ប៉ុន្តែបានរកឃើញគណនីស្រដៀងគ្នាចំនួន {len(other_matches)}៖*")

        for idx, m in enumerate(other_matches[:6], 1):
            u = m["username"]
            t = m["title"]
            k = m["type_km"]
            b = m.get("bio", "")
            lines.append(f"*{idx}.* *{t}* (`@{u}`)")
            lines.append(f"   • {k}")
            if b:
                lines.append(f"   • _{b[:60]}_")
            lines.append(f"   👉 [បើក Chat ➔ t.me/{u}]({m['url_https']})")
            lines.append("")

    lines.append("━━━━━━━━━━━━━━━━━━━━━━")
    lines.append("💡 _ចុចប៊ូតុងខាងក្រោមដើម្បី **បើកផ្ញើសារ (Chat Now)** ទៅកាន់គណនីដែលអ្នកចង់ទាក់ទងភ្លាមៗមួយចុច (1-Click)!_")

    # Add quick chat buttons for matches (up to 5 buttons)
    top_matches = [exact] if exact else []
    top_matches.extend([m for m in matches if not (exact and m["username"] == exact["username"])])
    
    for m in top_matches[:5]:
        u = m["username"]
        t = m["title"]
        btn_label = f"💬 Chat: @{u}" if len(u) <= 12 else f"💬 @{u}"
        buttons.append([InlineKeyboardButton(btn_label, url=m["url_https"])])

    buttons.append([InlineKeyboardButton("🔙 Menu ដើម", callback_data="btn_back_main")])

    return "\n".join(lines), InlineKeyboardMarkup(buttons)
