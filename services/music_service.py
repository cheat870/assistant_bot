import os
import shutil
import logging
import tempfile
import asyncio
from typing import Optional, Dict, Any
import yt_dlp

logger = logging.getLogger(__name__)

def _search_and_download_song_sync(query: str) -> Dict[str, Any]:
    """
    Search and download high-quality audio with anti-bot bypass.
    Strategy 1: High-speed YouTube Android player client (fetches official audio in 5-10s without bot check).
    Strategy 2: Multi-threaded SoundCloud fallback (5 concurrent fragments).
    """
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

    is_url = query.startswith("http://") or query.startswith("https://")
    is_sc_url = is_url and "soundcloud.com" in query.lower()

    # YouTube Options: Android player client completely bypasses datacenter bot detection & sign-in checks
    ydl_opts_yt = {
        "format": "bestaudio/best",
        "outtmpl": outtmpl,
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "ignoreerrors": True,
        "socket_timeout": 12,
        "retries": 1,
        "extractor_args": {
            "youtube": {
                "player_client": ["android"]
            }
        },
        "postprocessors": postprocessors,
    }

    # SoundCloud Options: High-speed 5x fragment downloads
    ydl_opts_sc = {
        "format": "bestaudio/best",
        "outtmpl": outtmpl,
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "ignoreerrors": True,
        "socket_timeout": 12,
        "retries": 1,
        "concurrent_fragment_downloads": 5,
        "postprocessors": postprocessors,
    }

    # If it is a direct SoundCloud URL, download via SoundCloud
    if is_sc_url:
        try:
            with yt_dlp.YoutubeDL(ydl_opts_sc) as ydl:
                info = ydl.extract_info(query, download=True)
                entry = info["entries"][0] if "entries" in info and info["entries"] else info
                return _process_downloaded_entry(entry, temp_dir)
        except Exception as e:
            logger.warning(f"Direct SoundCloud download failed: {e}")

    # Primary Strategy: YouTube with Android player client
    search_target_yt = query if is_url else f"ytsearch1:{query} audio"
    try:
        with yt_dlp.YoutubeDL(ydl_opts_yt) as ydl:
            info = ydl.extract_info(search_target_yt, download=True)
            if "entries" in info:
                valid_entries = [e for e in info.get("entries", []) if e]
                if valid_entries:
                    return _process_downloaded_entry(valid_entries[0], temp_dir)
            elif info:
                return _process_downloaded_entry(info, temp_dir)
    except Exception as e_yt:
        logger.warning(f"YouTube Android search failed ({e_yt}), falling back to SoundCloud...")

    # Secondary Strategy: SoundCloud search fallback
    search_target_sc = query if is_url else f"scsearch1:{query}"
    try:
        with yt_dlp.YoutubeDL(ydl_opts_sc) as ydl:
            info = ydl.extract_info(search_target_sc, download=True)
            if "entries" in info:
                valid_entries = [e for e in info.get("entries", []) if e]
                if valid_entries:
                    return _process_downloaded_entry(valid_entries[0], temp_dir)
            elif info:
                return _process_downloaded_entry(info, temp_dir)
    except Exception as e_sc:
        logger.error(f"SoundCloud fallback also failed: {e_sc}")

    # Clean up temp dir if all strategies failed
    try:
        shutil.rmtree(temp_dir, ignore_errors=True)
    except Exception:
        pass
    raise ValueError("រកមិនឃើញបទចម្រៀងដែលអ្នកចង់បានឡើយ។ សូមសាកល្បងវាយឈ្មោះបទ ឬឈ្មោះតារាចម្រៀងឱ្យកាន់តែច្បាស់។")

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
    dur_sec = int(duration) if duration else 0
    duration_min = f"{dur_sec // 60}:{dur_sec % 60:02d}" if dur_sec else "Unknown"

    return {
        "file_path": audio_file,
        "temp_dir": temp_dir,
        "title": title,
        "performer": uploader,
        "duration": dur_sec,
        "duration_str": duration_min,
        "thumbnail": thumbnail,
        "url": webpage_url
    }

async def download_song(query: str) -> Dict[str, Any]:
    """Async wrapper to search and download song audio with generous 75-second timeout."""
    return await asyncio.wait_for(
        asyncio.to_thread(_search_and_download_song_sync, query),
        timeout=75.0
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
        timeout=25.0
    )
