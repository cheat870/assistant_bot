import logging
import asyncio
import xml.etree.ElementTree as ET
import httpx
from typing import List, Dict, Any, Optional
from datetime import datetime
import pytz

logger = logging.getLogger(__name__)

CAMBODIA_RSS = "https://news.google.com/rss/search?q=Cambodia&hl=en-US&gl=US&ceid=US:en"
TECH_RSS = "https://news.google.com/rss/headlines/section/topic/TECHNOLOGY?hl=en-US&gl=US&ceid=US:en"

def _fetch_rss_items(url: str, limit: int = 3) -> List[Dict[str, str]]:
    """Synchronous RSS parser."""
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    try:
        with httpx.Client(timeout=10.0, follow_redirects=True) as client:
            resp = client.get(url, headers=headers)
            resp.raise_for_status()
            root = ET.fromstring(resp.content)
            items = []
            for item in root.findall(".//item")[:limit]:
                title = item.find("title").text if item.find("title") is not None else ""
                link = item.find("link").text if item.find("link") is not None else ""
                pub_date = item.find("pubDate").text if item.find("pubDate") is not None else ""
                source_elem = item.find("source")
                source = source_elem.text if source_elem is not None else "Google News"
                if title:
                    items.append({
                        "title": title,
                        "link": link,
                        "date": pub_date,
                        "source": source
                    })
            return items
    except Exception as e:
        logger.error(f"Error fetching RSS from {url}: {e}")
        return []

async def fetch_morning_headlines() -> Dict[str, List[Dict[str, str]]]:
    """Fetch top Cambodia national news and global tech news."""
    cambodia_news = await asyncio.to_thread(_fetch_rss_items, CAMBODIA_RSS, 3)
    tech_news = await asyncio.to_thread(_fetch_rss_items, TECH_RSS, 3)
    return {
        "cambodia": cambodia_news,
        "tech": tech_news
    }

async def generate_morning_news_digest() -> str:
    """Generate 7:00 AM Cambodia and Tech news digest in Khmer."""
    headlines_data = await fetch_morning_headlines()
    cam_items = headlines_data["cambodia"]
    tech_items = headlines_data["tech"]

    now_khmer = datetime.now(pytz.timezone("Asia/Phnom_Penh"))
    date_str = now_khmer.strftime("%d-%m-%Y")

    if not cam_items and not tech_items:
        return (
            f"📰 *ព្រឹត្តិបត្រព័ត៌មានពេលព្រឹក (Morning News Digest)*\n"
            f"📅 កាលបរិច្ឆេទ៖ {date_str}\n\n"
            f"⚠️ ពុំអាចទាញយកព័ត៌មានថ្មីៗនៅពេលនេះបានទេ។ សូមព្យាយាមម្តងទៀតតាមរយៈ `/news`។"
        )

    # Prepare raw summary text for AI formatting
    raw_lines = []
    raw_lines.append(f"Cambodia News:")
    for item in cam_items:
        raw_lines.append(f"- {item['title']} (Source: {item['source']})")
    raw_lines.append(f"\nTech News:")
    for item in tech_items:
        raw_lines.append(f"- {item['title']} (Source: {item['source']})")

    raw_text = "\n".join(raw_lines)

    # Attempt to summarize in elegant Khmer via Gemini
    from config import GEMINI_API_KEY
    if GEMINI_API_KEY and GEMINI_API_KEY != "your_gemini_api_key_here":
        try:
            from services.ai_service import _call_gemini_api
            from google import genai
            client = genai.Client(api_key=GEMINI_API_KEY)
            ai_prompt = (
                f"You are the chief morning news editor for Cambodian audiences. "
                f"Translate and summarize the following news headlines into top 5 concise, informative Khmer bullet points "
                f"(split between Cambodia national news and Technology news). Format with beautiful emojis, clean layout, "
                f"and include the date ({date_str}). Keep it engaging, easy to read on mobile, and polite.\n\n"
                f"{raw_text}"
            )
            # Fast AI summary with 5-second timeout; fallback immediately to clean digest if AI is busy
            resp = await asyncio.wait_for(
                asyncio.to_thread(_call_gemini_api, client, ai_prompt),
                timeout=5.0
            )
            return (
                f"🌅 *ព្រឹត្តិបត្រព័ត៌មានពេលព្រឹក ៧:០០ AM*\n"
                f"📅 កាលបរិច្ឆេទ៖ {date_str}\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"{resp.text}\n\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"💡 _ប្រើពាក្យបញ្ជា_ `/weather` _ដើម្បីពិនិត្យអាកាសធាតុ ឬ_ `/finance` _ដើម្បីពិនិត្យអត្រាប្តូរប្រាក់!_"
            )
        except Exception as e:
            logger.warning(f"Could not summarize news with AI (timeout/demand spike): {e}")

    # Fallback formatting without AI
    msg = f"🌅 *ព្រឹត្តិបត្រព័ត៌មានពេលព្រឹក ៧:០០ AM*\n"
    msg += f"📅 កាលបរិច្ឆេទ៖ {date_str}\n"
    msg += f"━━━━━━━━━━━━━━━━━━━━━━\n\n"

    if cam_items:
        msg += f"🇰🇭 *ព័ត៌មានជាតិកម្ពុជា៖*\n"
        for idx, item in enumerate(cam_items, 1):
            msg += f"{idx}. *{item['title']}*\n   _ប្រភព៖ {item['source']}_\n"
        msg += "\n"

    if tech_items:
        msg += f"💻 *ព័ត៌មានបច្ចេកវិទ្យាពិភពលោក (Tech Trends)：*\n"
        for idx, item in enumerate(tech_items, 1):
            msg += f"{idx}. *{item['title']}*\n   _ប្រភព៖ {item['source']}_\n"
        msg += "\n"

    msg += "━━━━━━━━━━━━━━━━━━━━━━\n"
    msg += "💡 _ប្រើពាក្យបញ្ជា_ `/weather` _ដើម្បីពិនិត្យអាកាសធាតុ ឬ_ `/rate` _ដើម្បីពិនិត្យអត្រាប្តូរប្រាក់!_"
    return msg
