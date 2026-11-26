import logging
import asyncio
import time
import html
import re
import urllib.parse
import xml.etree.ElementTree as ET
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
import pytz
import httpx

logger = logging.getLogger(__name__)

# Multi-Category News Hub Configuration
NEWS_CATEGORIES: Dict[str, Dict[str, str]] = {
    "national": {
        "title_km": "🇰🇭 ព័ត៌មានជាតិ & សង្គម",
        "desc_km": "ព្រឹត្តិការណ៍ជាតិ សង្គម និងកិច្ចការទូទៅនៅកម្ពុជា",
        "url": "https://news.google.com/rss/search?q=Cambodia+news&hl=en-US&gl=US&ceid=US:en",
    },
    "business": {
        "title_km": "💼 សេដ្ឋកិច្ច & ធុរកិច្ច",
        "desc_km": "សេដ្ឋកិច្ច ធនាគារ អចលនទ្រព្យ ពាណិជ្ជកម្ម និងទីផ្សារការងារ",
        "url": "https://news.google.com/rss/search?q=Cambodia+business+OR+economy+OR+real+estate+OR+trade&hl=en-US&gl=US&ceid=US:en",
    },
    "tech": {
        "title_km": "🤖 បច្ចេកវិទ្យា & AI Trends",
        "desc_km": "បច្ចេកវិទ្យា AI ឧបករណ៍ឆ្លាតវៃ ទូរស័ព្ទ និង App ពេញនិយម",
        "url": "https://news.google.com/rss/headlines/section/topic/TECHNOLOGY?hl=en-US&gl=US&ceid=US:en",
    },
    "sports": {
        "title_km": "⚽ កីឡាជាតិ & អន្តរជាតិ",
        "desc_km": "បាល់ទាត់ Premier League, Champions League និងកីឡាកម្ពុជា",
        "url": "https://news.google.com/rss/search?q=football+OR+Premier+League+OR+Champions+League+OR+Cambodia+sports&hl=en-US&gl=US&ceid=US:en",
    },
    "crypto": {
        "title_km": "🪙 ទីផ្សារ Crypto & Web3",
        "desc_km": "ព័ត៌មាន Bitcoin, TON, Ethereum និងបច្ចេកវិទ្យា Blockchain",
        "url": "https://news.google.com/rss/search?q=Bitcoin+OR+Crypto+OR+TON+Coin+OR+Ethereum&hl=en-US&gl=US&ceid=US:en",
    },
    "world": {
        "title_km": "🌍 ព័ត៌មានពិភពលោក",
        "desc_km": "ព្រឹត្តិការណ៍ក្តៅៗជុំវិញពិភពលោក និងភូមិសាស្ត្រនយោបាយ",
        "url": "https://news.google.com/rss/headlines/section/topic/WORLD?hl=en-US&gl=US&ceid=US:en",
    },
    "local": {
        "title_km": "📰 សារព័ត៌មានកម្ពុជា",
        "desc_km": "ស្រង់ផ្ទាល់ពី Fresh News, ThmeyThmey, Koh Santepheap, EAC News & RFI",
        "url": "https://news.google.com/rss/search?q=site:freshnewsasia.com+OR+site:thmeythmey.com+OR+site:kohsantepheapdaily.com.kh+OR+site:eacnews.asia&hl=en-US&gl=US&ceid=US:en",
    },
}

_category_cache: Dict[str, Dict[str, Any]] = {}
NEWS_CACHE_TTL = 900.0  # 15 minutes cache per category

def _clean_title(raw_title: str, source: str) -> str:
    """Clean RSS title and strip redundant source suffix."""
    title = html.unescape(raw_title).strip()
    if source and f" - {source}" in title:
        title = title.rsplit(f" - {source}", 1)[0].strip()
    elif " - " in title:
        parts = title.rsplit(" - ", 1)
        if len(parts[1]) < 30:
            title = parts[0].strip()
    return title

def _fetch_rss_items(url: str, limit: int = 5) -> List[Dict[str, str]]:
    """Fetch and parse RSS items with robust XML handling."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "application/rss+xml, application/xml, text/xml, */*"
    }
    try:
        with httpx.Client(timeout=10.0, follow_redirects=True) as client:
            resp = client.get(url, headers=headers)
            resp.raise_for_status()
            root = ET.fromstring(resp.content)
            items = []
            for item in root.findall(".//item")[:limit]:
                raw_title = item.find("title").text if item.find("title") is not None else ""
                link = item.find("link").text if item.find("link") is not None else ""
                pub_date = item.find("pubDate").text if item.find("pubDate") is not None else ""
                source_elem = item.find("source")
                source = source_elem.text if source_elem is not None else "Google News"
                
                if raw_title:
                    clean_t = _clean_title(raw_title, source)
                    items.append({
                        "title": clean_t,
                        "raw_title": raw_title,
                        "link": link.strip(),
                        "date": pub_date.strip(),
                        "source": source.strip()
                    })
            return items
    except Exception as e:
        logger.error(f"Error fetching RSS from {url}: {e}")
        return []

async def fetch_category_news(category: str = "national", limit: int = 5) -> List[Dict[str, str]]:
    """Fetch headlines for a specific category asynchronously."""
    cat_info = NEWS_CATEGORIES.get(category, NEWS_CATEGORIES["national"])
    return await asyncio.to_thread(_fetch_rss_items, cat_info["url"], limit)

async def search_custom_news(query: str, limit: int = 5) -> List[Dict[str, str]]:
    """Search Google News for custom keyword asynchronously."""
    encoded_q = urllib.parse.quote(query.strip())
    url = f"https://news.google.com/rss/search?q={encoded_q}&hl=en-US&gl=US&ceid=US:en"
    return await asyncio.to_thread(_fetch_rss_items, url, limit)

async def generate_category_news_card(category: str = "national", force_refresh: bool = False) -> Tuple[str, List[Dict[str, str]]]:
    """Generate interactive category news card with Gemini summary or rule-based Khmer fallback."""
    cat_key = category if category in NEWS_CATEGORIES else "national"
    cat_info = NEWS_CATEGORIES[cat_key]

    now_ts = time.time()
    cached = _category_cache.get(cat_key)
    if not force_refresh and cached and (now_ts - cached["time"] < NEWS_CACHE_TTL):
        return cached["text"], cached["items"]

    items = await fetch_category_news(cat_key, limit=5)

    now_khmer = datetime.now(pytz.timezone("Asia/Phnom_Penh"))
    date_str = now_khmer.strftime("%d-%m-%Y %I:%M %p")

    if not items:
        msg = (
            f"📰 *[{cat_info['title_km']}]*\n"
            f"🕒 បច្ចុប្បន្នភាព៖ `{date_str}`\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"⚠️ ពុំទាន់មានព័ត៌មានថ្មីក្នុងប្រភេទទូរទស្សន៍នេះនៅឡើយទេ ឬកំពុងតភ្ជាប់បណ្តាញយឺត។\n"
            f"សូមចុចប៊ូតុង *«🔄 Refresh ព័ត៌មាន»* ឬជ្រើសរើសប្រភេទផ្សេងទៀតខាងក្រោម។"
        )
        return msg, []

    # Attempt AI summary translation via Gemini
    from config import GEMINI_API_KEY
    if GEMINI_API_KEY and GEMINI_API_KEY != "your_gemini_api_key_here":
        try:
            from services.ai_service import _call_gemini_api
            from google import genai
            client = genai.Client(api_key=GEMINI_API_KEY)

            raw_bullets = "\n".join([f"- [{it['source']}] {it['title']} ({it['link']})" for it in items])
            prompt = (
                f"You are the senior Khmer news editor for a Telegram assistant bot.\n"
                f"Task: Translate and summarize these {cat_info['title_km']} headlines into 5 clean, engaging Khmer bullet points.\n"
                f"Guidelines:\n"
                f"1. Use natural, accurate Cambodian Khmer with relevant emojis for each story.\n"
                f"2. Keep each story to 1-2 concise lines explaining what happened clearly.\n"
                f"3. Include source credit in parentheses (e.g. [ប្រភព៖ Fresh News]).\n"
                f"4. Do NOT output markdown links inside parentheses that break Telegram parser.\n"
                f"5. Output ONLY the 5 numbered bullet points.\n\n"
                f"Headlines:\n{raw_bullets}"
            )
            resp = await asyncio.wait_for(
                asyncio.to_thread(_call_gemini_api, client, prompt),
                timeout=12.0
            )
            ai_text = resp.text.strip()
            
            card = (
                f"📰 *[{cat_info['title_km']}]* ✨\n"
                f"📝 _{cat_info['desc_km']}_\n"
                f"🕒 បច្ចុប្បន្នភាព៖ `{date_str}`\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"{ai_text}\n\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"💡 _ចុចប៊ូតុងប្រភេទព័ត៌មានខាងក្រោមដើម្បីប្តូរប្រធានបទភ្លាមៗ!_"
            )
            _category_cache[cat_key] = {"text": card, "items": items, "time": now_ts}
            return card, items
        except Exception as e:
            logger.warning(f"AI news translation fallback: {e}")

    # Fallback formatting without AI or offline
    lines = [
        f"📰 *[{cat_info['title_km']}]*",
        f"📝 _{cat_info['desc_km']}_",
        f"🕒 បច្ចុប្បន្នភាព៖ `{date_str}`",
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
    ]
    for idx, it in enumerate(items, 1):
        lines.append(f"{idx}. *{it['title']}*")
        lines.append(f"   🏷️ _ប្រភព៖ {it['source']}_ | [🔗 អានប្រភពដើម]({it['link']})\n")

    lines.append("━━━━━━━━━━━━━━━━━━━━━━")
    lines.append("💡 _ចុចប៊ូតុងប្រភេទព័ត៌មានខាងក្រោមដើម្បីប្តូរប្រធានបទភ្លាមៗ!_")
    card = "\n".join(lines)
    _category_cache[cat_key] = {"text": card, "items": items, "time": now_ts}
    return card, items

async def generate_search_news_card(query: str) -> str:
    """Generate search results for a user custom keyword query."""
    clean_q = query.strip()
    if not clean_q:
        return "🔍 សូមវាយពាក្យគន្លឹះដែលចង់ស្វែងរក (ឧទាហរណ៍៖ `/news គម្រោងព្រែកជីក` ឬ `/news iPhone 17`)"

    items = await search_custom_news(clean_q, limit=5)
    now_khmer = datetime.now(pytz.timezone("Asia/Phnom_Penh"))
    date_str = now_khmer.strftime("%d-%m-%Y %I:%M %p")

    if not items:
        return (
            f"🔍 *លទ្ធផលស្វែងរកព័ត៌មាន៖* «{clean_q}»\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"❌ រកមិនឃើញព័ត៌មានថ្មីៗពាក់ព័ន្ធនឹង «{clean_q}» ក្នុងរយៈពេល ២៤ ម៉ោងចុងក្រោយនេះទេ។\n"
            f"💡 _សូមសាកល្បងជាមួយពាក្យគន្លឹះផ្សេងទៀត។_"
        )

    lines = [
        f"🔍 *លទ្ធផលស្វែងរកព័ត៌មាន៖* «{clean_q}» ⚡",
        f"🕒 ស្វែងរកនៅម៉ោង៖ `{date_str}`",
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
    ]
    for idx, it in enumerate(items, 1):
        lines.append(f"{idx}. *{it['title']}*")
        lines.append(f"   🏷️ _ប្រភព៖ {it['source']}_ | [🔗 អានអត្ថបទ]({it['link']})\n")

    lines.append("━━━━━━━━━━━━━━━━━━━━━━")
    lines.append("💡 _ចុច /news ដើម្បីត្រឡប់ទៅផ្ទាំងព័ត៌មានចម្រុះ (News Hub)_")
    return "\n".join(lines)

async def fetch_morning_headlines() -> Dict[str, List[Dict[str, str]]]:
    """Fetch top Cambodia national news and global tech news for scheduler backward compatibility."""
    cambodia_news = await fetch_category_news("national", 3)
    tech_news = await fetch_category_news("tech", 3)
    return {
        "cambodia": cambodia_news,
        "tech": tech_news
    }

async def generate_morning_news_digest(force_refresh: bool = False) -> str:
    """Generate 7:00 AM Cambodia and Tech news digest for daily scheduler (backward compatible)."""
    card, _ = await generate_category_news_card("national", force_refresh=force_refresh)
    return card
