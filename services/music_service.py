import os
import re
import shutil
import logging
import tempfile
import asyncio
from typing import Optional, Dict, Any, List
import yt_dlp

logger = logging.getLogger(__name__)

def _get_ffmpeg_path() -> Optional[str]:
    """Find system ffmpeg or imageio-ffmpeg bundled binary."""
    sys_ffmpeg = shutil.which("ffmpeg")
    if sys_ffmpeg:
        return sys_ffmpeg
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None

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
    - Strategy 1: Fast single-step YouTube search & direct download with multi-client anti-bot bypass.
    - Strategy 2: Multi-query YouTube fallback with 'audio' / 'full song'.
    - Strategy 3: SoundCloud fallback with DRM protection tolerance & token matching.
    """
    temp_dir = tempfile.mkdtemp(prefix="song_")
    outtmpl = os.path.join(temp_dir, "%(id)s.%(ext)s")

    ffmpeg_exe = _get_ffmpeg_path()
    postprocessors = []
    if ffmpeg_exe:
        postprocessors.append({
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "320",
        })

    is_url = query.startswith("http://") or query.startswith("https://")
    is_sc_url = is_url and "soundcloud.com" in query.lower()

    # Robust options with android client bypass for datacenter/cloud bot checks
    ydl_opts_base = {
        "format": "bestaudio/best",
        "outtmpl": outtmpl,
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "ignoreerrors": True,
        "socket_timeout": 15,
        "retries": 2,
        "extractor_args": {
            "youtube": {
                "player_client": ["android"]
            }
        },
        "postprocessors": postprocessors,
    }
    if ffmpeg_exe:
        ydl_opts_base["ffmpeg_location"] = ffmpeg_exe

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

    # 3. Primary Strategy: Fast YouTube Search with Single-Step Direct Download
    yt_search_queries = [
        f"ytsearch1:{query}",
        f"ytsearch1:{query} audio",
        f"ytsearch1:{query} full song",
    ]

    last_error = ""
    for search_target in yt_search_queries:
        for client_candidate in [["android"], ["android_vr"], None]:
            try:
                opts = dict(ydl_opts_base)
                if client_candidate:
                    opts["extractor_args"] = {"youtube": {"player_client": client_candidate}}
                else:
                    opts.pop("extractor_args", None)

                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(search_target, download=True)
                    if not info or "entries" not in info or not info["entries"]:
                        continue
                    entry = info["entries"][0]
                    if not entry:
                        continue

                    # Filter out short clips/teasers (< 45 seconds)
                    dur = entry.get("duration") or 0
                    if dur >= 45 or search_target == yt_search_queries[-1]:
                        return _process_downloaded_entry(entry, temp_dir)
            except Exception as e_yt:
                last_error = str(e_yt)
                logger.warning(f"YouTube search attempt '{search_target}' with client {client_candidate} failed: {e_yt}")

    # 4. Secondary Strategy: SoundCloud search fallback (strictly >50s, DRM-safe, relevant match)
    try:
        ydl_opts_sc = dict(ydl_opts_base)
        ydl_opts_sc["concurrent_fragment_downloads"] = 5
        with yt_dlp.YoutubeDL(ydl_opts_sc) as ydl:
            # Process=False extracts playlist entries without evaluating DRM on every track
            info = ydl.extract_info(f"scsearch5:{query}", download=False, process=False)
            if info and "entries" in info and info["entries"]:
                query_tokens = [w.lower() for w in re.split(r'[\s\-_|/]+', query) if len(w) >= 3]
                for raw_entry in info["entries"]:
                    if not raw_entry:
                        continue
                    sc_url = raw_entry.get("url")
                    if not sc_url:
                        continue

                    # Safely probe individual candidate
                    try:
                        sc_info = ydl.extract_info(sc_url, download=False)
                    except Exception:
                        continue
                    if not sc_info or (sc_info.get("duration") or 0) <= 50 or sc_info.get("drm"):
                        continue

                    sc_text = f"{sc_info.get('title', '')} {sc_info.get('uploader', '')}".lower()
                    if query_tokens and not any(t in sc_text for t in query_tokens):
                        continue

                    ydl.process_ie_result(sc_info, download=True)
                    return _process_downloaded_entry(sc_info, temp_dir)
    except Exception as e_sc:
        logger.warning(f"SoundCloud fallback failed: {e_sc}")

    # Clean up temp dir if all strategies failed
    try:
        shutil.rmtree(temp_dir, ignore_errors=True)
    except Exception:
        pass
    err_detail = f" (មូលហេតុបច្ចេកទេស: {last_error[:80]})" if last_error else ""
    raise ValueError(f"រកមិនឃើញបទចម្រៀងពេញលេញដែលអ្នកចង់បានឡើយ។ សូមសាកល្បងវាយឈ្មោះបទ ឬឈ្មោះតារាចម្រៀងឱ្យកាន់តែច្បាស់។{err_detail}")

def _process_downloaded_entry(entry: Dict[str, Any], temp_dir: str) -> Dict[str, Any]:
    """Helper to locate downloaded file, sanitize format for Telegram, and package clean metadata."""
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

    # Prefer native audio formats (.mp3, .m4a, .ogg, .flac)
    audio_candidates = [
        f for f in downloaded_files
        if any(f.lower().endswith(ext) for ext in [".mp3", ".m4a", ".ogg", ".flac", ".wav"])
    ]
    if audio_candidates:
        audio_file = audio_candidates[0]
    else:
        # If only muxed video/audio (.mp4) was downloaded, rename to .m4a so Telegram accepts it as native audio
        fallback_file = downloaded_files[0]
        if fallback_file.lower().endswith(".mp4"):
            m4a_file = os.path.splitext(fallback_file)[0] + ".m4a"
            os.rename(fallback_file, m4a_file)
            audio_file = m4a_file
        else:
            audio_file = fallback_file

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
