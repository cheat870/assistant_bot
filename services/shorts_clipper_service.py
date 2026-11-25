import os
import re
import json
import uuid
import logging
import asyncio
import subprocess
from pathlib import Path
from typing import Tuple, Optional, Dict, Any

import yt_dlp
from config import GEMINI_API_KEY
from services.video_editor_service import get_ffmpeg_binary

logger = logging.getLogger(__name__)

DOWNLOAD_DIR = Path("downloads")
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

async def auto_clip_viral_shorts(url: str) -> Tuple[bool, Optional[str], str, Optional[Dict[str, Any]]]:
    """
    Download a video and use Gemini AI to detect and clip the most viral 30-60 second segment.
    Returns: (success, clipped_video_path, message_or_title, metadata)
    """
    try:
        # Step 1: Extract Video Info and Transcript/Description using yt-dlp
        ydl_opts = {
            'skip_download': True,
            'quiet': True,
            'no_warnings': True,
            'writesubtitles': True,
            'writeautomaticsub': True,
            'subtitleslangs': ['en', 'km'],
        }

        loop = asyncio.get_event_loop()
        info = await loop.run_in_executor(None, lambda: yt_dlp.YoutubeDL(ydl_opts).extract_info(url, download=False))
        if not info:
            return False, None, "❌ មិនអាចទាញយកទិន្នន័យវីដេអូបានទេ។", None

        title = info.get('title', 'Video')
        duration = info.get('duration', 0)
        description = (info.get('description') or "")[:1500]

        if duration < 35:
            return False, None, f"⚠️ វីដេអូនេះខ្លីពេកស្រាប់ហើយ ({duration} វិនាទី) មិនបាច់កាត់បន្ថែមទៀតឡើយ។", None

        # Step 2: Ask Gemini AI to find the viral 30-60s window
        from google import genai
        from google.genai import types
        from services.ai_service import _call_gemini_api

        client = genai.Client(api_key=GEMINI_API_KEY)
        prompt = (
            f"You are a viral TikTok and Reels content strategist.\n"
            f"Video Title: {title}\n"
            f"Duration: {duration} seconds\n"
            f"Description/Summary: {description}\n\n"
            "Task: Identify the single most engaging, dramatic, exciting, or funny 30 to 60 second moment to clip as a viral Short/Reel.\n"
            "Requirements:\n"
            "1. start_time (in seconds, must be between 0 and duration - 30)\n"
            "2. end_time (in seconds, must be 30 to 60 seconds after start_time, <= duration)\n"
            "3. hook_title: Catchy viral hook title in Khmer\n"
            "4. viral_reason: Brief explanation why this 30-60s part is engaging\n\n"
            "Return STRICT JSON only, e.g.:\n"
            '{"start_time": 45, "end_time": 95, "hook_title": "...", "viral_reason": "..."}'
        )

        response = await asyncio.to_thread(
            _call_gemini_api,
            client,
            prompt,
            "Identify viral hook segment strictly as JSON."
        )

        res_text = response.text.strip() if response and response.text else "{}"
        if res_text.startswith("```"):
            res_text = re.sub(r"^```[a-zA-Z]*\n?", "", res_text)
            res_text = re.sub(r"\n?```$", "", res_text).strip()

        try:
            plan = json.loads(res_text)
            start_sec = max(0, int(plan.get("start_time", 15)))
            end_sec = min(duration, int(plan.get("end_time", start_sec + 45)))
            if end_sec - start_sec < 25 or end_sec - start_sec > 75:
                end_sec = min(duration, start_sec + 45)
            hook_title = plan.get("hook_title", title).strip()
            viral_reason = plan.get("viral_reason", "ឈុតឆាកជក់ចិត្ត").strip()
        except Exception:
            start_sec = 10 if duration > 50 else 0
            end_sec = min(duration, start_sec + 45)
            hook_title = f"Viral Clip - {title[:30]}"
            viral_reason = "ឈុតឆាកពេញនិយម និងទាក់ទាញបំផុត"

        # Step 3: Download and cut exact segment using ffmpeg
        unique_id = uuid.uuid4().hex[:8]
        out_clip_path = DOWNLOAD_DIR / f"viral_short_{unique_id}.mp4"

        # Choose best format under 45MB
        ydl_clip_opts = {
            'format': 'bestvideo[height<=1080][filesize_approx<?40M]+bestaudio/best[filesize_approx<?40M]/best',
            'outtmpl': str(DOWNLOAD_DIR / f"raw_source_{unique_id}.%(ext)s"),
            'quiet': True,
            'no_warnings': True,
            'merge_output_format': 'mp4',
        }

        # Download raw source
        raw_info = await loop.run_in_executor(None, lambda: yt_dlp.YoutubeDL(ydl_clip_opts).extract_info(url, download=True))
        raw_file = None
        for f in DOWNLOAD_DIR.glob(f"raw_source_{unique_id}*"):
            if f.is_file():
                raw_file = f
                break

        if not raw_file or not raw_file.exists():
            return False, None, "❌ មិនអាចទាញយកប្រភពវីដេអូដើមដើម្បីកាត់បានទេ។", None

        # Step 4: Run FFmpeg trim
        ffmpeg_bin = get_ffmpeg_binary()
        clip_duration = end_sec - start_sec

        cmd = [
            ffmpeg_bin,
            "-y",
            "-ss", str(start_sec),
            "-i", str(raw_file),
            "-t", str(clip_duration),
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "22",
            "-c:a", "aac",
            "-b:a", "128k",
            "-avoid_negative_ts", "make_zero",
            str(out_clip_path)
        ]

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        _, stderr = await proc.communicate()

        # Clean up raw download to save disk space
        try:
            raw_file.unlink(missing_ok=True)
        except Exception:
            pass

        if proc.returncode != 0 or not out_clip_path.exists():
            err_msg = stderr.decode(errors="ignore")[:100]
            return False, None, f"❌ បរាជ័យក្នុងការ Render វីដេអូខ្លី៖ {err_msg}", None

        # Format helper time strings
        def fmt_time(sec):
            m, s = divmod(int(sec), 60)
            return f"{m:02d}:{s:02d}"

        meta = {
            "hook_title": hook_title,
            "viral_reason": viral_reason,
            "start_time": fmt_time(start_sec),
            "end_time": fmt_time(end_sec),
            "clip_duration": clip_duration,
            "original_title": title,
        }

        return True, str(out_clip_path), hook_title, meta

    except Exception as e:
        logger.error(f"Error in auto_clip_viral_shorts: {e}")
        return False, None, f"❌ កំហុសបច្ចេកទេសក្នុងការកាត់វីដេអូ Viral Shorts៖ {str(e)[:120]}", None
