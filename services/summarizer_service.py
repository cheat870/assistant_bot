import os
import re
import uuid
import logging
from pathlib import Path
from typing import Optional, Dict, Any
import yt_dlp

from config import GEMINI_API_KEY, DOWNLOAD_DIR

logger = logging.getLogger(__name__)

def extract_video_transcript(url: str) -> Dict[str, Any]:
    """
    Extract transcript text and metadata from a video using yt-dlp without downloading media.
    Returns dict with 'title', 'channel', 'transcript', 'duration'.
    """
    unique_id = uuid.uuid4().hex[:8]
    sub_template = str(DOWNLOAD_DIR / f"sum_sub_{unique_id}_%(id)s.%(ext)s")

    ydl_opts = {
        'skip_download': True,
        'writesubtitles': True,
        'writeautomaticsub': True,
        'subtitleslangs': ['en', 'km', 'id', 'es', 'zh'],
        'subtitlesformat': 'vtt',
        'outtmpl': sub_template,
        'quiet': True,
        'no_warnings': True,
        'source_address': '0.0.0.0',
        'socket_timeout': 25,
        'extractor_args': {
            'youtube': {
                'player_client': ['android', 'ios', 'tv_embedded'],
                'player_skip': ['webpage', 'configs']
            }
        }
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if not info:
                return {"success": False, "error": "មិនអាចទាញយកព័ត៌មានវីដេអូបានទេ"}

            title = info.get("title", "Video")
            channel = info.get("uploader") or info.get("channel", "Unknown")
            duration = info.get("duration", 0)
            description = info.get("description", "")

            # Look for written subtitle files
            sub_files = list(DOWNLOAD_DIR.glob(f"sum_sub_{unique_id}_*"))
            full_transcript = ""

            if sub_files:
                sub_path = sub_files[0]
                try:
                    content = sub_path.read_text(encoding="utf-8", errors="ignore")
                    # Clean VTT header and timestamps
                    lines = []
                    for line in content.splitlines():
                        line_str = line.strip()
                        if not line_str or line_str.startswith("WEBVTT") or "-->" in line_str or line_str.isdigit():
                            continue
                        # Strip html tags in subtitles
                        cleaned = re.sub(r"<[^>]+>", "", line_str).strip()
                        if cleaned and (not lines or lines[-1] != cleaned):
                            lines.append(cleaned)
                    full_transcript = " ".join(lines)
                except Exception as e_read:
                    logger.warning(f"Failed reading sub file: {e_read}")
                finally:
                    for sf in sub_files:
                        try:
                            sf.unlink()
                        except Exception:
                            pass

            # Fallback to description if transcript not available
            if not full_transcript or len(full_transcript) < 50:
                full_transcript = description[:3000]

            return {
                "success": True,
                "title": title,
                "channel": channel,
                "duration": duration,
                "transcript": full_transcript[:12000] # Feed up to 12k chars to Gemini
            }

    except Exception as e:
        logger.error(f"Error extracting transcript: {e}")
        return {"success": False, "error": str(e)}

async def summarize_video_ai(url: str) -> str:
    """
    Summarize a video into structured Khmer takeaways using Gemini AI.
    """
    data = extract_video_transcript(url)
    if not data.get("success"):
        return f"❌ មិនអាចសង្ខេបវីដេអូនេះបានទេ៖ {data.get('error', 'Unknown')}"

    title = data.get("title", "Video")
    channel = data.get("channel", "Unknown")
    transcript = data.get("transcript", "")

    if not transcript or len(transcript) < 30:
        return (
            f"🎬 *{title}*\n"
            f"👤 *Channel:* {channel}\n\n"
            f"⚠️ វីដេអូនេះគ្មាន Subtitles/Transcript សម្រាប់ឱ្យ AI វិភាគឡើយ។"
        )

    dur_sec = data.get("duration", 0)
    dur_str = f"{dur_sec // 60}:{dur_sec % 60:02d}" if dur_sec else "N/A"

    prompt = (
        f"ចំណងជើងវីដេអូ៖ {title}\n"
        f"អ្នកបង្កើត៖ {channel}\n"
        f"រយៈពេល៖ {dur_str}\n\n"
        f"Transcript សំដីក្នុងវីដេអូ៖\n{transcript}\n\n"
        f"សូមសង្ខេបខ្លឹមសារវីដេអូនេះជាភាសាខ្មែរ ឱ្យមានលក្ខណៈទាក់ទាញ ក្បោះក្បាយ ចែកជា ៣ ផ្នែកច្បាស់លាស់៖\n"
        f"១. 📌 *ប្រធានបទគោល (Executive Summary)*\n"
        f"២. 🔑 *ចំណុចសំខាន់ៗ (Key Takeaways / Bullet points)*\n"
        f"៣. 💡 *មេរៀន ឬអនុសាសន៍ (Conclusion)*\n"
        f"សរសេរជាទម្រង់ Telegram Markdown ស្អាត និងមាន Emoji សមរម្យ។"
    )

    try:
        from services.ai_service import query_ai
        summary_text = await query_ai(prompt)
        header = f"📝 *[AI Video Summarizer - សង្ខេបវីដេអូ]* ✨\n🎬 *{title}* ({dur_str})\n👤 *Channel:* `{channel}`\n\n"
        return header + summary_text
    except Exception as e:
        logger.error(f"AI summarizer error: {e}")
        return f"❌ កំហុសក្នុងការសង្ខេបដោយ AI៖ {str(e)[:120]}"
