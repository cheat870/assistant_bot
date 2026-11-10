import os
import re
import shutil
import logging
import tempfile
import asyncio
from typing import Optional, Dict, Any, List
import yt_dlp

logger = logging.getLogger(__name__)

def _clean_music_metadata(raw_title: str, raw_uploader: str) -> tuple[str, str]:
    """Clean up clutter from YouTube/SoundCloud titles and artist names."""
    title = raw_title or "Unknown Title"
    uploader = raw_uploader or "Unknown Artist"

    # Remove YouTube channel suffixes
    if uploader.endswith(" - Topic"):
        uploader = uploader[:-8].strip()

    # If title has "Artist - Title", extract them
    if " - " in title and (not uploader or uploader in ["Unknown Artist", "Unknown"]):
        parts = title.split(" - ", 1)
        uploader = parts[0].strip()
        title = parts[1].strip()

    # Clean clutter tags from title
    clutter_patterns = [
        r'\[Official\s*(?:Music\s*)?Video\]',
        r'\(Official\s*(?:Music\s*)?Video\)',
        r'\[Official\s*Audio\]',
        r'\(Official\s*Audio\)',
        r'\[Official\s*HD\s*Video\]',
        r'\(Official\s*HD\s*Video\)',
        r'\[Official\s*Visualizer\]',
        r'\(Official\s*Visualizer\)',
        r'\[(?:Official\s*)?MV\]',
        r'\((?:Official\s*)?MV\)',
        r'\|\s*Official\s*MV',
        r'\|\s*Official\s*Music\s*Video',
        r'\(Lyrics\)',
        r'\[Lyrics\]',
        r'\(Lyric\s*Video\)',
        r'\[Lyric\s*Video\]',
        r'\(Audio\)',
        r'\[Audio\]',
        r'\(Full\s*Song\)',
        r'\[Full\s*Song\]',
    ]
    for pat in clutter_patterns:
        title = re.sub(pat, '', title, flags=re.IGNORECASE)

    return title.strip(), uploader.strip()

def _search_and_download_song_sync(query: str) -> Dict[str, Any]:
    """
    Search and download full-length audio (MP3 320kbps / M4A) with smart candidate filtering.
    - Strategy 1: YouTube 2-stage search (filters out <45s shorts/snippets to guarantee full 3-5min song).
    - Strategy 2: Multi-query YouTube fallback with 'official audio'.
    - Strategy 3: SoundCloud fallback with strict duration filter (rejects all 30-second Go+ previews).
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

    # High-speed options with Android client bypass for datacenter/cloud bot checks
    ydl_opts_base = {
        "format": "bestaudio[ext=m4a]/bestaudio/best",
        "outtmpl": outtmpl,
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "ignoreerrors": True,
        "socket_timeout": 15,
        "retries": 2,
        "extractor_args": {
            "youtube": {
                "player_client": ["android", "web"]
            }
        },
        "postprocessors": postprocessors,
    }

    # 1. Direct SoundCloud URL
    if is_sc_url:
        try:
            with yt_dlp.YoutubeDL(ydl_opts_base) as ydl:
                info = ydl.extract_info(query, download=True)
                entry = info["entries"][0] if "entries" in info and info["entries"] else info
                return _process_downloaded_entry(entry, temp_dir)
        except Exception as e:
            logger.warning(f"Direct SoundCloud download failed: {e}")

    # 2. Direct Video / Audio URL (e.g. YouTube URL)
    if is_url:
        try:
            with yt_dlp.YoutubeDL(ydl_opts_base) as ydl:
                info = ydl.extract_info(query, download=True)
                entry = info["entries"][0] if "entries" in info and info["entries"] else info
                return _process_downloaded_entry(entry, temp_dir)
        except Exception as e:
            logger.warning(f"Direct URL download failed: {e}")

    # 3. Primary Strategy: Fast 1-to-1 YouTube Search with Android Anti-Bot Bypass
    # Uses ytsearch1 for 1.5s ultra-fast response without datacenter rate limits
    yt_search_queries = [
        f"ytsearch1:{query}",
        f"ytsearch1:{query} audio",
        f"ytsearch1:{query} full song",
    ]

    for search_target in yt_search_queries:
        try:
            with yt_dlp.YoutubeDL(ydl_opts_base) as ydl:
                info = ydl.extract_info(search_target, download=False)
                if not info or "entries" not in info or not info["entries"]:
                    continue
                entry = info["entries"][0]
                if not entry:
                    continue

                # Filter out short clips/teasers (< 45 seconds)
                dur = entry.get("duration") or 0
                if dur >= 45 or search_target == yt_search_queries[-1]:
                    # Download the verified full track
                    web_url = entry.get("webpage_url") or f"https://www.youtube.com/watch?v={entry.get('id')}"
                    ydl.download([web_url])
                    return _process_downloaded_entry(entry, temp_dir)
        except Exception as e_yt:
            logger.warning(f"YouTube search attempt '{search_target}' failed: {e_yt}")

    # 4. Secondary Strategy: SoundCloud search fallback (strictly >50s, no DRM)
    try:
        ydl_opts_sc = dict(ydl_opts_base)
        ydl_opts_sc["concurrent_fragment_downloads"] = 5
        with yt_dlp.YoutubeDL(ydl_opts_sc) as ydl:
            info = ydl.extract_info(f"scsearch1:{query}", download=False)
            if info and "entries" in info and info["entries"]:
                sc_entry = info["entries"][0]
                if sc_entry and (sc_entry.get("duration") or 0) > 50 and not sc_entry.get("drm"):
                    ydl.process_ie_result(sc_entry, download=True)
                    return _process_downloaded_entry(sc_entry, temp_dir)
    except Exception as e_sc:
        logger.warning(f"SoundCloud fallback failed: {e_sc}")

    # Clean up temp dir if all strategies failed
    try:
        shutil.rmtree(temp_dir, ignore_errors=True)
    except Exception:
        pass
    raise ValueError("រកមិនឃើញបទចម្រៀងពេញលេញដែលអ្នកចង់បានឡើយ។ សូមសាកល្បងវាយឈ្មោះបទ ឬឈ្មោះតារាចម្រៀងឱ្យកាន់តែច្បាស់។")

def _process_downloaded_entry(entry: Dict[str, Any], temp_dir: str) -> Dict[str, Any]:
    """Helper to locate downloaded file and package clean metadata."""
    raw_title = entry.get("title", "Unknown Title")
    raw_uploader = entry.get("uploader") or entry.get("artist") or "Unknown Artist"
    duration = entry.get("duration", 0)
    thumbnail = entry.get("thumbnail")
    webpage_url = entry.get("webpage_url")

    title, performer = _clean_music_metadata(raw_title, raw_uploader)

    # Find the downloaded audio file in temp_dir
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
        "performer": performer,
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
