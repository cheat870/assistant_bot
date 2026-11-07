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
    Prioritizes fast multi-threaded SoundCloud search (never blocks datacenter IPs, 5x concurrent downloads)
    and falls back to mobile-client YouTube.
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
    is_yt_url = is_url and any(yt in query.lower() for yt in ["youtube.com", "youtu.be"])

    ydl_opts_sc = {
        "format": "bestaudio/best",
        "outtmpl": outtmpl,
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "ignoreerrors": True,
        "socket_timeout": 15,
        "retries": 2,
        "concurrent_fragment_downloads": 5,
        "postprocessors": postprocessors,
    }

    ydl_opts_yt = {
        "format": "bestaudio/best",
        "outtmpl": outtmpl,
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "ignoreerrors": True,
        "socket_timeout": 15,
        "retries": 1,
        "extractor_args": {
            "youtube": {
                "player_client": ["mweb", "ios", "android_creator"]
            }
        },
        "postprocessors": postprocessors,
    }

    # If it is a direct YouTube link, prioritize YouTube downloader
    if is_yt_url:
        try:
            with yt_dlp.YoutubeDL(ydl_opts_yt) as ydl:
                info = ydl.extract_info(query, download=True)
                entry = info["entries"][0] if "entries" in info and info["entries"] else info
                return _process_downloaded_entry(entry, temp_dir)
        except Exception as e:
            logger.warning(f"Direct YouTube download failed: {e}")

    # Primary Strategy for Search: SoundCloud (instant 5-8s download, never challenges datacenter IPs)
    search_target_sc = query if is_url else f"scsearch3:{query}"
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
        logger.warning(f"SoundCloud search failed ({e_sc}), falling back to YouTube...")

    # Secondary Strategy: YouTube search with mobile client bypass
    search_target_yt = query if is_url else f"ytsearch1:{query}"
    try:
        with yt_dlp.YoutubeDL(ydl_opts_yt) as ydl:
            info = ydl.extract_info(search_target_yt, download=True)
            if "entries" in info:
                if not info["entries"]:
                    raise ValueError("រកមិនឃើញបទចម្រៀងដែលអ្នកចង់បានឡើយ")
                entry = info["entries"][0]
            else:
                entry = info

            return _process_downloaded_entry(entry, temp_dir)
    except Exception as e_yt:
        logger.error(f"YouTube search fallback also failed: {e_yt}")
        try:
            shutil.rmtree(temp_dir, ignore_errors=True)
        except Exception:
            pass
        raise ValueError("មិនអាចទាញយកបទចម្រៀងនេះបានទេ។ សូមសាកល្បងវាយឈ្មោះបទ ឬឈ្មោះតារាចម្រៀងម្តងទៀត។")

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
        "duration": duration,
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
