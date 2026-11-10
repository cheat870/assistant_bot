import re
import html
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
            "• ឧទាហរណ៍៖ `/user Dawincyy14`\n"
            "• ឧទាហរណ៍៖ `/whois @lyheak`\n\n"
            "Bot នឹងស្វែងរក និងបង្ហាញរូប Profile Picture និងលេខទូរស័ព្ទ (Phone) ជូនភ្លាមៗ! 🚀"
        )
        
    clean = extract_telegram_username(raw_text)
    if not clean or len(clean) < 2:
        return (
            False,
            "",
            "⚠️ *សូមវាយឈ្មោះយ៉ាងហោចណាស់ ២ តួអក្សរឡើងទៅ!* ឧទាហរណ៍៖ `/user heamlyheak`"
        )
        
    return True, clean, ""

def detect_cambodia_carrier(phone_str: str) -> str:
    """Detect Cambodian mobile telecom operator by prefix."""
    digits = ''.join(c for c in phone_str if c.isdigit())
    if digits.startswith("855"):
        digits = "0" + digits[3:]
    prefix3 = digits[:3]
    if prefix3 in ["010", "015", "016", "069", "070", "081", "086", "087", "093", "096", "098"]:
        return "Smart Axiata 🟢"
    if prefix3 in ["011", "012", "014", "017", "061", "076", "077", "078", "079", "085", "089", "092", "095", "099"]:
        return "Cellcard 🟠"
    if prefix3 in ["031", "060", "066", "067", "068", "071", "088", "090", "097"]:
        return "Metfone 🔴"
    if prefix3 in ["018"]:
        return "Seatel 🔵"
    return "Cambodia Mobile 📱"

def extract_cambodian_phones(text: str) -> List[Dict[str, str]]:
    """Extract Cambodian phone numbers and detect telecom operator."""
    if not text:
        return []
    raw_matches = re.findall(r'(?:\+?855[\s.-]?|0)[1-9][0-9\s.-]{6,11}', text)
    results = []
    seen = set()
    for m in raw_matches:
        digits = re.sub(r'\D', '', m)
        if len(digits) in [9, 10, 11, 12]:
            clean_digits = "0" + digits[3:] if digits.startswith("855") else digits
            if clean_digits not in seen:
                seen.add(clean_digits)
                carrier = detect_cambodia_carrier(clean_digits)
                results.append({
                    "raw": m.strip(),
                    "clean": clean_digits,
                    "carrier": carrier,
                })
    return results

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

async def check_telegram_public_web(client: httpx.AsyncClient, username: str, fetch_bytes: bool = False) -> Optional[Dict[str, Any]]:
    """Check if a username actually exists publicly on Telegram's web gateway, extracting photo & phone."""
    try:
        resp = await client.get(f"https://t.me/{username}")
        if resp.status_code != 200:
            return None
            
        html_raw = resp.text
        has_title = 'tgme_page_title' in html_raw
        has_photo = 'tgme_page_photo' in html_raw
        if not (has_title or has_photo):
            return None
            
        # 1. Title / Display Name
        title = ""
        mt = re.search(r'class=[\'"][^\'"]*tgme_page_title[^\'"]*[\'"][^>]*>(.*?)</div>', html_raw, re.DOTALL | re.IGNORECASE)
        if mt:
            title = html.unescape(re.sub(r'<[^>]+>', '', mt.group(1)).strip())
            
        # 2. Extra / Subscribers / Members
        extra = ""
        me = re.search(r'class=[\'"][^\'"]*tgme_page_extra[^\'"]*[\'"][^>]*>(.*?)</div>', html_raw, re.DOTALL | re.IGNORECASE)
        if me:
            extra = html.unescape(re.sub(r'<[^>]+>', '', me.group(1)).strip())
            
        # 3. Bio / Description
        bio = ""
        mb = re.search(r'class=[\'"][^\'"]*tgme_page_description[^\'"]*[\'"][^>]*>(.*?)</div>', html_raw, re.DOTALL | re.IGNORECASE)
        if mb:
            bio = html.unescape(re.sub(r'<[^>]+>', '', mb.group(1)).strip())
        if not bio:
            og_desc = re.search(r'<meta\s+property=[\'"]og:description[\'"]\s+content=[\'"]([^\'"]+)[\'"]', html_raw, re.IGNORECASE)
            if og_desc:
                bio = html.unescape(og_desc.group(1).strip())

        # 4. Profile Picture URL & Bytes
        photo_url = None
        photo_bytes = None
        m_og_img = re.search(r'<meta\s+property=[\'"]og:image[\'"]\s+content=[\'"](https?://[^\'"]+)[\'"]', html_raw, re.IGNORECASE)
        if m_og_img and "telegram.org/img" not in m_og_img.group(1):
            photo_url = m_og_img.group(1)
        else:
            m_img = re.search(r'class=[\'"][^\'"]*tgme_page_photo_image[^\'"]*[\'"][^>]*src=[\'"](https?://[^\'"]+)[\'"]', html_raw, re.IGNORECASE)
            if m_img and "telegram.org/img" not in m_img.group(1):
                photo_url = m_img.group(1)

        # Download photo bytes if requested or if available
        if photo_url and fetch_bytes:
            try:
                p_resp = await client.get(photo_url)
                if p_resp.status_code == 200 and len(p_resp.content) > 500:
                    photo_bytes = p_resp.content
            except Exception as e_p:
                logger.debug(f"Failed to fetch photo bytes: {e_p}")

        # 5. Extract Phone Numbers from Bio & Title
        extracted_phones = extract_cambodian_phones(f"{title} {bio}")

        # Deduce account type
        type_km = "គណនីផ្ទាល់ខ្លួន 👤"
        if "subscribers" in extra.lower() or "channel" in html_raw.lower():
            type_km = "ប៉ុស្តិ៍ Channel 📢"
        elif "members" in extra.lower() or "group" in html_raw.lower():
            type_km = "ក្រុម Group 👥"
        elif username.lower().endswith("bot") or "bot" in extra.lower():
            type_km = "Telegram Bot 🤖"
            
        return {
            "username": username,
            "title": title or username,
            "extra": extra,
            "bio": bio,
            "photo_url": photo_url,
            "photo_bytes": photo_bytes,
            "phones": extracted_phones,
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
    extracts profile photos & phone numbers across Telegram and local DB.
    """
    is_valid, clean_query, err_msg = validate_username_format(raw_query)
    if not is_valid:
        return {
            "valid": False,
            "error_msg": err_msg,
            "query": raw_query,
            "matches": [],
            "photo_url": None,
            "photo_bytes": None,
        }

    clean_single = re.sub(r'[^a-zA-Z0-9_]', '', clean_query.lower())
    candidates = generate_smart_candidates(clean_query)
    
    # 1. Real-time batch check across Telegram's gateway
    async with httpx.AsyncClient(timeout=5.0, headers=HTTP_HEADERS, follow_redirects=True) as client:
        # Check candidates (download bytes for primary clean_single if checked)
        results = await asyncio.gather(*[check_telegram_public_web(client, c, fetch_bytes=(c == clean_single)) for c in candidates])
        
        found_map: Dict[str, Dict[str, Any]] = {}
        for r in results:
            if r and r["username"] not in found_map:
                found_map[r["username"]] = r

        # If primary clean_single was found and doesn't have photo_bytes yet, fetch them;
        # otherwise ensure top candidate with photo has bytes downloaded
        top_cand_u = clean_single if (clean_single in found_map and found_map[clean_single].get("photo_url")) else None
        if not top_cand_u:
            for u_cand, data_cand in found_map.items():
                if data_cand.get("photo_url"):
                    top_cand_u = u_cand
                    break

        if top_cand_u and not found_map[top_cand_u].get("photo_bytes"):
            try:
                p_resp = await client.get(found_map[top_cand_u]["photo_url"])
                if p_resp.status_code == 200 and len(p_resp.content) > 500:
                    found_map[top_cand_u]["photo_bytes"] = p_resp.content
            except Exception as e_fetch:
                logger.debug(f"Failed to fetch top photo bytes for @{top_cand_u}: {e_fetch}")

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
                "photo_url": None,
                "photo_bytes": None,
                "phones": [],
                "type_km": "គណនីក្នុងប្រព័ន្ធ Bot 💾",
                "url_https": f"https://t.me/{u_name}",
                "url_tg": f"tg://resolve?domain={u_name}",
            }

    matches_list = list(found_map.values())
    exact_match = found_map.get(clean_single)

    # Determine top photo URL & bytes to send
    top_photo_url = None
    top_photo_bytes = None
    if exact_match and (exact_match.get("photo_bytes") or exact_match.get("photo_url")):
        top_photo_url = exact_match.get("photo_url")
        top_photo_bytes = exact_match.get("photo_bytes")
    elif matches_list:
        for m in matches_list:
            if m.get("photo_bytes") or m.get("photo_url"):
                top_photo_url = m.get("photo_url")
                top_photo_bytes = m.get("photo_bytes")
                break

    return {
        "valid": True,
        "query": clean_query,
        "clean_single": clean_single,
        "exact_match": exact_match,
        "matches": matches_list,
        "photo_url": top_photo_url,
        "photo_bytes": top_photo_bytes,
    }

def format_user_resolver_card(data: Dict[str, Any]) -> Tuple[str, InlineKeyboardMarkup]:
    """
    Format report card displaying profiles, phone numbers, and direct chat buttons.
    Ensures message is clean, compact, and under 950 characters to safely fit photo captions.
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
        f"🔍 *លទ្ធផលស្វែងរកគណនី Telegram & Profile: \"{query}\"* ✨",
        "━━━━━━━━━━━━━━━━━━━━━━",
    ]

    # If exact match exists, highlight it at the top
    if exact:
        lines.append("🎯 *គណនីត្រូវគ្នា ១០០% (Exact Match)៖*")
        lines.append(f"• *Username:* `@{exact['username']}`")
        lines.append(f"• *ឈ្មោះបង្ហាញ (Name):* *{exact['title']}*")
        lines.append(f"• *ប្រភេទគណនី:* {exact['type_km']}")
        
        # Phone number
        phones = exact.get("phones", [])
        if phones:
            phone_strs = [f"`{p['clean']}` ({p['carrier']})" for p in phones]
            lines.append(f"• 📞 *លេខទូរស័ព្ទ (Phone):* {', '.join(phone_strs)}")
        else:
            lines.append("• 📞 *លេខទូរស័ព្ទ:* _(ម្ចាស់គណនីបានលាក់ Private)_")

        if exact.get("bio"):
            lines.append(f"• *Bio / ពិពណ៌នា:* _{exact['bio'][:100]}_")
            
        lines.append(f"👉 [ចុចបើក Chat (t.me/{exact['username']})]({exact['url_https']})")
        lines.append("")

    # List all similar matches (limit to top 4 to stay well under caption limit)
    other_matches = [m for m in matches if not (exact and m["username"] == exact["username"])]
    if other_matches:
        count_label = f" ({len(other_matches)})" if len(other_matches) > 1 else ""
        if exact:
            lines.append(f"👥 *គណនីស្រដៀងគ្នាផ្សេងទៀតដែលបានរកឃើញ{count_label}៖*")
        else:
            lines.append(f"⚠️ *មិនមាន Username ជាក់លាក់ `@{clean_single}` ឡើយ ប៉ុន្តែបានរកឃើញគណនីស្រដៀងគ្នាចំនួន {len(other_matches)}៖*")

        for idx, m in enumerate(other_matches[:4], 1):
            u = m["username"]
            t = m["title"]
            k = m["type_km"]
            b = m.get("bio", "")
            phones = m.get("phones", [])
            lines.append(f"*{idx}.* *{t}* (`@{u}`)")
            lines.append(f"   • {k}")
            if phones:
                p_strs = [f"`{p['clean']}` ({p['carrier']})" for p in phones]
                lines.append(f"   • 📞 *Phone:* {', '.join(p_strs)}")
            if b:
                lines.append(f"   • 📝 _{b[:50]}_")
            lines.append(f"   👉 [បើក Chat ➔ t.me/{u}]({m['url_https']})")
            lines.append("")

    lines.append("━━━━━━━━━━━━━━━━━━━━━━")
    lines.append("💡 _ចុចប៊ូតុងខាងក្រោមដើម្បី **បើកផ្ញើសារ (Chat Now)** ភ្លាមៗ (1-Click)!_")

    # Add quick chat buttons for matches (up to 4 buttons)
    top_matches = [exact] if exact else []
    top_matches.extend([m for m in matches if not (exact and m["username"] == exact["username"])])
    
    for m in top_matches[:4]:
        u = m["username"]
        btn_label = f"💬 Chat: @{u}" if len(u) <= 12 else f"💬 @{u}"
        buttons.append([InlineKeyboardButton(btn_label, url=m["url_https"])])

    buttons.append([InlineKeyboardButton("🔙 Menu ដើម", callback_data="btn_back_main")])

    final_text = "\n".join(lines)
    # Ensure it is strictly under 1000 characters
    if len(final_text) > 980:
        final_text = final_text[:970] + "\n..."

    return final_text, InlineKeyboardMarkup(buttons)
