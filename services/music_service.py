import os
import shutil
import logging
import tempfile
import asyncio
from typing import Optional, Dict, Any
import yt_dlp

logger = logging.getLogger(__name__)

def _search_and_download_song_sync(query: str) -> Dict[str, Any]:
    """Search YouTube for query and download high-quality audio."""
    temp_dir = tempfile.mkdtemp(prefix="song_")
    outtmpl = os.path.join(temp_dir, "%(id)s.%(ext)s")

    has_ffmpeg = shutil.which("ffmpeg") is not None

    postprocessors = []
    if has_ffmpeg:
        postprocessors.append({
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "320",
        })

    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": outtmpl,
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "default_search": "ytsearch1:",
        "postprocessors": postprocessors,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        # Search query
        search_target = query if query.startswith("http://") or query.startswith("https://") else f"ytsearch1:{query}"
        info = ydl.extract_info(search_target, download=True)
        
        # If search returned entries list
        if "entries" in info:
            if not info["entries"]:
                raise ValueError("រកមិនឃើញបទចម្រៀងដែលអ្នកចង់បានឡើយ")
            entry = info["entries"][0]
        else:
            entry = info

        title = entry.get("title", "Unknown Title")
        uploader = entry.get("uploader", "Unknown Artist")
        duration = entry.get("duration", 0)
        thumbnail = entry.get("thumbnail")
        webpage_url = entry.get("webpage_url")

        # Find the downloaded file in temp_dir
        downloaded_files = [
            os.path.join(temp_dir, f) for f in os.listdir(temp_dir)
            if not f.endswith(".part") and not f.endswith(".ytdl")
        ]
        if not downloaded_files:
            raise FileNotFoundError("បរាជ័យក្នុងការទាញយក file សំឡេង")

        audio_file = downloaded_files[0]
        duration_min = f"{duration // 60}:{duration % 60:02d}" if duration else "Unknown"

        return {
            "file_path": audio_file,
            "temp_dir": temp_dir,
            "title": title,
            "performer": uploader,
            "duration": duration,
            "duration_str": duration_min,
            "thumbnail": thumbnail,
            "url": webpage_url
        }

async def download_song(query: str) -> Dict[str, Any]:
    """Async wrapper to search and download song audio."""
    return await asyncio.to_thread(_search_and_download_song_sync, query)

def _identify_tiktok_sound_sync(url: str) -> Dict[str, Any]:
    """Extract audio/sound metadata from a TikTok or social video URL."""
    ydl_opts = {
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        track = info.get("track")
        artist = info.get("artist")
        album = info.get("album")
        title = info.get("title", "Unknown Video")
        uploader = info.get("uploader", "Unknown")

        return {
            "title": title,
            "track": track or "Soundtrack ដើម",
            "artist": artist or uploader,
            "album": album or "TikTok Original",
            "url": url
        }

async def identify_tiktok_sound(url: str) -> Dict[str, Any]:
    """Async wrapper to inspect audio metadata from TikTok video."""
    return await asyncio.to_thread(_identify_tiktok_sound_sync, url)
