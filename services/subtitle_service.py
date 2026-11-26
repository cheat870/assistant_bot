import os
import re
import uuid
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List
import yt_dlp

from config import GEMINI_API_KEY, DOWNLOAD_DIR

logger = logging.getLogger(__name__)

def vtt_timestamp_to_srt(ts: str) -> str:
    """Convert VTT timestamp (00:01.500 or 00:00:01.500) to SRT format (00:00:01,500)."""
    ts = ts.strip().replace(".", ",")
    parts = ts.split(":")
    if len(parts) == 2:
        return f"00:{parts[0].zfill(2)}:{parts[1]}"
    elif len(parts) == 3:
        return f"{parts[0].zfill(2)}:{parts[1].zfill(2)}:{parts[2]}"
    return ts

def parse_vtt_cues(vtt_text: str) -> List[Dict[str, str]]:
    """Parse VTT subtitle content into structured cues with start, end, and text."""
    cues = []
    blocks = vtt_text.replace("\r\n", "\n").split("\n\n")
    for block in blocks:
        lines = [l.strip() for l in block.split("\n") if l.strip()]
        if not lines:
            continue
        # Find line with timestamp arrow -->
        ts_line_idx = -1
        for i, l in enumerate(lines):
            if "-->" in l:
                ts_line_idx = i
                break
        if ts_line_idx == -1:
            continue

        ts_parts = lines[ts_line_idx].split("-->")
        start_ts = vtt_timestamp_to_srt(ts_parts[0])
        end_ts = vtt_timestamp_to_srt(ts_parts[1].split()[0]) # strip any extra position metadata

        dialogue_lines = lines[ts_line_idx + 1:]
        clean_text = " ".join(dialogue_lines)
        clean_text = re.sub(r"<[^>]+>", "", clean_text).strip()

        if clean_text:
            cues.append({
                "start": start_ts,
                "end": end_ts,
                "text": clean_text
            })
    return cues

async def translate_cues_to_khmer(cues: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """Translate subtitle cue texts to natural Khmer using Gemini AI."""
    if not GEMINI_API_KEY or not cues:
        return cues

    # Limit to first 120 cues to prevent API token explosion on huge movies
    cues_to_translate = cues[:120]
    numbered_lines = [f"{i+1}. {c['text']}" for i, c in enumerate(cues_to_translate)]
    combined_prompt = "\n".join(numbered_lines)

    instruction = (
        "You are an expert film subtitle translator. "
        "Translate the following numbered subtitle lines into natural, conversational, fluent Khmer. "
        "Keep the exact same line numbering (e.g., '1. ...', '2. ...'). "
        "Do not skip lines or change the numbers."
    )

    try:
        from google import genai
        client = genai.Client(api_key=GEMINI_API_KEY)
        resp = await client.aio.models.generate_content(
            model="gemini-2.5-flash",
            contents=f"{instruction}\n\n{combined_prompt}",
        )
        if resp and resp.text:
            trans_lines = resp.text.strip().splitlines()
            trans_map = {}
            for l in trans_lines:
                match = re.match(r"^(\d+)\.\s*(.*)", l.strip())
                if match:
                    trans_map[int(match.group(1))] = match.group(2).strip()

            for i, c in enumerate(cues_to_translate):
                if (i + 1) in trans_map and trans_map[i + 1]:
                    c["text"] = trans_map[i + 1]
    except Exception as e:
        logger.warning(f"Error translating cues with Gemini: {e}")
        # Fallback to free Google Translate for cues
        try:
            import httpx, urllib.parse
            # Combine up to 40 cues with newline
            batch = "\n".join([c["text"] for c in cues_to_translate[:40]])
            url = f"https://translate.googleapis.com/translate_a/single?client=gtx&sl=auto&tl=km&dt=t&q={urllib.parse.quote(batch)}"
            async with httpx.AsyncClient(timeout=15.0) as client:
                r = await client.get(url)
                if r.status_code == 200:
                    translated_chunks = [item[0] for item in r.json()[0] if item and item[0]]
                    translated_text = "".join(translated_chunks)
                    lines = [l.strip() for l in translated_text.splitlines() if l.strip()]
                    for i in range(min(len(lines), len(cues_to_translate))):
                        if lines[i]:
                            cues_to_translate[i]["text"] = lines[i]
        except Exception as e_gt:
            logger.warning(f"Fallback translation error: {e_gt}")

    return cues_to_translate

async def generate_khmer_subtitles(url: str) -> Dict[str, Any]:
    """
    Download subtitles, translate them to Khmer, and compile an official .srt file.
    Returns dict with success, file_path, title, preview_text.
    """
    unique_id = uuid.uuid4().hex[:8]
    sub_template = str(DOWNLOAD_DIR / f"rawsub_{unique_id}_%(id)s.%(ext)s")

    ydl_opts = {
        'skip_download': True,
        'writesubtitles': True,
        'writeautomaticsub': True,
        'subtitleslangs': ['en', 'km'],
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
        title = "Video"
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if info:
                title = info.get("title", "Video")

        sub_files = list(DOWNLOAD_DIR.glob(f"rawsub_{unique_id}_*"))
        if not sub_files:
            return {"success": False, "error": "វីដេអូនេះគ្មាន Subtitles/Captions ឡើយ"}

        vtt_path = sub_files[0]
        vtt_text = vtt_path.read_text(encoding="utf-8", errors="ignore")
        vtt_path.unlink(missing_ok=True)

        cues = parse_vtt_cues(vtt_text)
        if not cues:
            return {"success": False, "error": "មិនអាចស្វែងរកទិន្នន័យអត្ថបទក្នុង Subtitle បានទេ"}

        translated_cues = await translate_cues_to_khmer(cues)

        # Build .srt file
        srt_content = []
        for i, c in enumerate(translated_cues):
            srt_content.append(f"{i+1}")
            srt_content.append(f"{c['start']} --> {c['end']}")
            srt_content.append(f"{c['text']}\n")

        clean_title = re.sub(r'[\/:*?"<>|]', '_', title)[:30]
        srt_filename = f"{clean_title}_Khmer_Subtitles_{unique_id}.srt"
        srt_path = DOWNLOAD_DIR / srt_filename
        srt_path.write_text("\n".join(srt_content), encoding="utf-8")

        preview = "\n".join([f"⏱️ `{c['start'][:8]}` : {c['text']}" for c in translated_cues[:5]])

        return {
            "success": True,
            "file_path": str(srt_path),
            "filename": srt_filename,
            "title": title,
            "cues_count": len(translated_cues),
            "preview_text": preview
        }

    except Exception as e:
        logger.error(f"Error generating subtitles: {e}")
        return {"success": False, "error": str(e)[:120]}
