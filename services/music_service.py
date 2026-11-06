import os
import shutil
import logging
import tempfile
import asyncio
from typing import Optional, Dict, Any
import yt_dlp

logger = logging.getLogger(__name__)

def _search_and_download_song_sync(query: str) -> Dict[str, Any]:
    """Search YouTube or SoundCloud for query and download high-quality audio with anti-bot bypass."""
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

    # Strategy 1: YouTube with mobile & embedded player clients to bypass datacenter bot detection
    ydl_opts_yt = {
        "format": "bestaudio/best",
        "outtmpl": outtmpl,
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "socket_timeout": 15,
        "retries": 2,
        "extractor_args": {
            "youtube": {
                "player_client": ["android", "ios", "web_embedded"]
            }
        },
        "postprocessors": postprocessors,
    }

    last_err = None
    search_target_yt = query if query.startswith("http://") or query.startswith("https://") else f"ytsearch1:{query}"
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts_yt) as ydl:
            info = ydl.extract_info(search_target_yt, download=True)
            if "entries" in info:
                if not info["entries"]:
                    raise ValueError("រកមិនឃើញបទចម្រៀងដែលអ្នកចង់បាននៅលើ YouTube ឡើយ")
                entry = info["entries"][0]
            else:
                entry = info

            return _process_downloaded_entry(entry, temp_dir)
    except Exception as e:
        logger.warning(f"YouTube download failed ({e}), falling back to SoundCloud search...")
        last_err = e

    # Strategy 2: SoundCloud Fallback (Never blocks datacenter IPs)
    search_target_sc = query if query.startswith("http://") or query.startswith("https://") else f"scsearch1:{query}"
    ydl_opts_sc = {
        "format": "bestaudio/best",
        "outtmpl": outtmpl,
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "socket_timeout": 15,
        "retries": 2,
        "postprocessors": postprocessors,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts_sc) as ydl:
            info = ydl.extract_info(search_target_sc, download=True)
            if "entries" in info:
                if not info["entries"]:
                    raise ValueError("រកមិនឃើញបទចម្រៀងដែលអ្នកចង់បានឡើយ")
                entry = info["entries"][0]
            else:
                entry = info

            return _process_downloaded_entry(entry, temp_dir)
    except Exception as e_sc:
        logger.error(f"SoundCloud fallback also failed: {e_sc}")
        # Clean up temp dir if failed
        try:
            shutil.rmtree(temp_dir, ignore_errors=True)
        except Exception:
            pass
        raise last_err or e_sc

def _process_downloaded_entry(entry: Dict[str, Any], temp_dir: str) -> Dict[str, Any]:
    """Helper to locate downloaded file and package metadata."""
    title = entry.get("title", "Unknown Title")
    uploader = entry.get("uploader") or entry.get("artist") or "Unknown Artist"
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
    """Async wrapper to search and download song audio with strict 35-second timeout."""
    return await asyncio.wait_for(
        asyncio.to_thread(_search_and_download_song_sync, query),
        timeout=35.0
    )

def _identify_tiktok_sound_sync(url: str) -> Dict[str, Any]:
    """Extract audio/sound metadata from a TikTok or social video URL."""
    ydl_opts = {
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "socket_timeout": 15,
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
            "uploader": uploader,
            "url": url
        }

async def identify_tiktok_sound(url: str) -> Dict[str, Any]:
    """Async wrapper to extract audio metadata."""
    return await asyncio.wait_for(
        asyncio.to_thread(_identify_tiktok_sound_sync, url),
        timeout=20.0
    )
