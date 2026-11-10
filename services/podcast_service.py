import io
import re
import logging
import asyncio
from typing import Dict, Any, Optional
import httpx

from services.tts_service import generate_tts_audio
from services.ai_service import _call_gemini_api, format_gemini_error
from config import GEMINI_API_KEY

logger = logging.getLogger(__name__)

HTTP_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "km,en-US;q=0.9,en;q=0.8"
}

PODCAST_PROMPT = (
    "You are an elite Cambodian Radio Host and Audio Podcast Anchor. "
    "A listener shared a news article or web story. "
    "Carefully analyze this article title and text to create a dual summary in fluent, natural Khmer:\n\n"
    "Output formatted exactly as follows:\n"
    "===SUMMARY===\n"
    "📰 *ចំណងជើង:* {Title in Khmer}\n\n"
    "💡 *សង្ខេបខ្លឹមសារសំខាន់ៗ ៣ ចំណុច៖*\n"
    "• {Key Point 1}\n"
    "• {Key Point 2}\n"
    "• {Key Point 3}\n\n"
    "🔍 *សេចក្តីសន្និដ្ឋាន/ផលប៉ះពាល់:* {1-line takeaway}\n"
    "===SPOKEN===\n"
    "{Write a lively, natural, professional spoken script in Khmer (around 90 to 140 words) that sounds great when read aloud on a radio show. "
    "Start warmly with 'សួស្តីប្រិយមិត្តអ្នកស្តាប់ទាំងអស់គ្នា! នេះជារបាយការណ៍ព័ត៌មានសង្ខេប...', narrate the essence clearly, and end with a polite sign-off. "
    "Do NOT use markdown, emojis, asterisks, or parentheses in this spoken section so text-to-speech reads it smoothly.}"
)

async def extract_article_content_from_url(url: str) -> Dict[str, Any]:
    """Fetch webpage HTML and clean extracted main body text and title."""
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True, headers=HTTP_HEADERS) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                return {"success": False, "title": "Web Article", "text": "", "url": url}

            html = resp.text

            # Extract Title
            title = "អត្ថបទព័ត៌មាន"
            og_title = re.search(r'<meta\s+property=["\']og:title["\']\s+content=["\'](.*?)["\']', html, re.IGNORECASE)
            if og_title:
                title = og_title.group(1).strip()
            else:
                tag_title = re.search(r'<title>(.*?)</title>', html, re.IGNORECASE)
                if tag_title:
                    title = tag_title.group(1).split("-")[0].split("|")[0].strip()

            # Clean HTML tags
            clean_html = re.sub(r'<script.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
            clean_html = re.sub(r'<style.*?</style>', '', clean_html, flags=re.DOTALL | re.IGNORECASE)
            clean_html = re.sub(r'<nav.*?</nav>', '', clean_html, flags=re.DOTALL | re.IGNORECASE)
            clean_html = re.sub(r'<header.*?</header>', '', clean_html, flags=re.DOTALL | re.IGNORECASE)
            clean_html = re.sub(r'<footer.*?</footer>', '', clean_html, flags=re.DOTALL | re.IGNORECASE)

            # Extract paragraphs
            paragraphs = re.findall(r'<p[^>]*>(.*?)</p>', clean_html, flags=re.DOTALL | re.IGNORECASE)
            text_lines = []
            for p in paragraphs:
                cleaned_p = re.sub(r'<[^>]+>', '', p).strip()
                if len(cleaned_p) > 25:
                    text_lines.append(cleaned_p)

            body_text = "\n".join(text_lines[:15])  # Take first 15 substantive paragraphs
            return {
                "success": bool(body_text),
                "title": title,
                "text": body_text[:4000],
                "url": url
            }
    except Exception as e:
        logger.warning(f"Error extracting article from {url}: {e}")
        return {"success": False, "title": "Web Article", "text": "", "url": url}

async def generate_article_podcast(url: str) -> Dict[str, Any]:
    """
    Scrape article, summarize key points, and generate a Khmer audio podcast MP3.
    Returns: {"title": title, "bullet_summary": str, "audio_bytes": bytes, "spoken_text": str}
    """
    article = await extract_article_content_from_url(url)
    if not article.get("success") or not article.get("text"):
        return {
            "success": False,
            "title": article.get("title", "អត្ថបទ"),
            "bullet_summary": "❌ មិនអាចទាញយកខ្លឹមសារពីគេហទំព័រនេះបានទេ។ សូមពិនិត្យមើល Link ឬសាកល្បងវេបសាយព័ត៌មានផ្សេងទៀត!",
            "audio_bytes": b"",
            "spoken_text": ""
        }

    title = article["title"]
    body = article["text"]

    prompt = (
        f"{PODCAST_PROMPT}\n\n"
        f"Article Title: '{title}'\n"
        f"Article URL: {url}\n\n"
        f"Article Body Content:\n{body}"
    )

    bullet_summary = ""
    spoken_text = ""

    if GEMINI_API_KEY and GEMINI_API_KEY != "your_gemini_api_key_here":
        from google import genai
        client = genai.Client(api_key=GEMINI_API_KEY)
        try:
            resp = await asyncio.to_thread(_call_gemini_api, client, prompt)
            raw = resp.text
            if "===SUMMARY===" in raw and "===SPOKEN===" in raw:
                parts = raw.split("===SPOKEN===")
                bullet_summary = parts[0].replace("===SUMMARY===", "").strip()
                spoken_text = parts[1].strip()
            else:
                bullet_summary = raw.strip()
                spoken_text = f"សួស្តីប្រិយមិត្តអ្នកស្តាប់! នេះជាសេចក្តីសង្ខេបព័ត៌មាន៖ {title}។ សូមរីករាយស្តាប់ការសង្ខេបនេះ។"
        except Exception as e:
            logger.error(f"Gemini podcast generation error: {e}")
            bullet_summary = f"📰 *{title}*\n\n" + body[:300] + "..."
            spoken_text = f"សួស្តី! នេះជាព័ត៌មានស្តីពី {title}។"
    else:
        bullet_summary = f"📰 *{title}*\n\n" + body[:300] + "..."
        spoken_text = f"សួស្តី! នេះជាព័ត៌មានស្តីពី {title}។"

    # Generate MP3 Audio from spoken text
    try:
        audio_fp = generate_tts_audio(spoken_text, lang="km")
        audio_bytes = audio_fp.getvalue()
    except Exception as e_tts:
        logger.error(f"TTS audio synthesis error: {e_tts}")
        audio_bytes = b""

    return {
        "success": True,
        "title": title,
        "bullet_summary": bullet_summary,
        "audio_bytes": audio_bytes,
        "spoken_text": spoken_text,
        "url": url
    }
