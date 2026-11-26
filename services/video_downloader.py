import os
import re
import uuid
import asyncio
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List
import httpx
import yt_dlp

from config import DOWNLOAD_DIR, MAX_FILE_SIZE_MB

logger = logging.getLogger(__name__)

# URL pattern to match common video links
URL_REGEX = re.compile(
    r'https?://(?:www\.|vt\.|m\.|vm\.)?'
    r'(?:tiktok\.com|youtube\.com|youtu\.be|facebook\.com|fb\.watch|instagram\.com|twitter\.com|x\.com|threads\.net|pinterest\.com|reddit\.com|vimeo\.com)'
    r'/[^\s]+',
    re.IGNORECASE
)

def extract_video_url(text: str) -> Optional[str]:
    """Find video URL in text message."""
    if not text:
        return None
    match = URL_REGEX.search(text)
    if match:
        return match.group(0)
    general_match = re.search(r'https?://[^\s]+', text)
    if general_match:
        return general_match.group(0)
    return None

def is_tiktok_url(url: str) -> bool:
    """Check if URL is from TikTok."""
    return bool(re.search(r'tiktok\.com', url, re.IGNORECASE))

def is_youtube_url(url: str) -> bool:
    """Check if URL is from YouTube or YouTube Music."""
    return bool(re.search(r'(?:youtube\.com|youtu\.be)', url, re.IGNORECASE))

def clean_song_title(title: str) -> str:
    """Clean video title to extract the core artist & song name for music search."""
    clean = re.sub(r'[\(\[\{][^\)\]\}]*(?:official|audio|video|slow|remix|mv|lyric|lyrics|4k|hd|prod|beat)[^\)\]\}]*[\)\]\}]', '', title, flags=re.IGNORECASE)
    clean = re.sub(r'(?:official\s*audio|official\s*video|official\s*music\s*video|slow\s*remix|remix|slowed\s*\+\s*reverb)', '', clean, flags=re.IGNORECASE)
    clean = re.sub(r'\s+', ' ', clean).strip()
    return clean or title

def fetch_youtube_oembed(url: str) -> Optional[Dict[str, str]]:
    """
    Fetch authentic video metadata from YouTube public oEmbed endpoint without API key or IP blocks.
    Endpoint: https://www.youtube.com/oembed?url=...&format=json
    """
    try:
        import urllib.parse
        encoded_url = urllib.parse.quote(url, safe='')
        oembed_url = f"https://www.youtube.com/oembed?url={encoded_url}&format=json"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        }
        with httpx.Client(timeout=6.0, headers=headers, follow_redirects=True) as client:
            resp = client.get(oembed_url)
            if resp.status_code == 200:
                data = resp.json()
                return {
                    "title": data.get("title", ""),
                    "author_name": (data.get("author_name", "") or "").strip(),
                    "thumbnail_url": data.get("thumbnail_url", ""),
                }
    except Exception as e:
        logger.debug(f"oEmbed fetch failed for {url}: {e}")
    return None

class VideoDownloadResult:
    def __init__(
        self,
        success: bool,
        file_path: Optional[str] = None,
        title: Optional[str] = None,
        duration: Optional[int] = None,
        thumbnail_url: Optional[str] = None,
        uploader: Optional[str] = None,
        file_size_mb: float = 0.0,
        direct_web_url: Optional[str] = None,
        is_audio: bool = False,
        error_message: Optional[str] = None,
        images: Optional[List[str]] = None,
        is_photo_slideshow: bool = False,
        music_url: Optional[str] = None
    ):
        self.success = success
        self.file_path = file_path
        self.title = title or "Video"
        self.duration = duration
        self.thumbnail_url = thumbnail_url
        self.uploader = uploader or "Unknown"
        self.file_size_mb = file_size_mb
        self.direct_web_url = direct_web_url
        self.is_audio = is_audio
        self.error_message = error_message
        self.images = images or []
        self.is_photo_slideshow = is_photo_slideshow
        self.music_url = music_url

def _download_tiktok_api(url: str, download_folder: Path, audio_only: bool = False) -> VideoDownloadResult:
    """High-speed watermark-free TikTok downloader via dedicated API."""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        }
        with httpx.Client(timeout=30) as client:
            resp = client.post('https://www.tikwm.com/api/', data={'url': url, 'hd': 1})
            if resp.status_code != 200:
                return VideoDownloadResult(success=False, error_message="Failed to contact TikTok API service.")
            
            data = resp.json()
            if data.get('code') != 0:
                err_msg = data.get('msg', 'Unknown TikTok error')
                return VideoDownloadResult(success=False, error_message=f"TikTok Error: {err_msg}")
            
            video_info = data.get('data', {})
            images_list = video_info.get('images') or []

            # Handle TikTok Photo Slideshow / Live Photos mode
            if images_list and not audio_only:
                saved_images = []
                total_bytes = 0
                unique_id = str(uuid.uuid4())[:8]
                title = video_info.get('title') or "TikTok Photos"
                author = video_info.get('author', {}).get('nickname') or "TikTok Creator"
                music_url = video_info.get('music') or video_info.get('play')

                for idx, img_u in enumerate(images_list[:20]):
                    try:
                        img_resp = client.get(img_u, headers=headers, follow_redirects=True)
                        if img_resp.status_code == 200:
                            img_path = download_folder / f"tiktok_img_{unique_id}_{idx+1}.jpg"
                            img_path.write_bytes(img_resp.content)
                            saved_images.append(str(img_path))
                            total_bytes += len(img_resp.content)
                    except Exception:
                        continue

                if saved_images:
                    file_size_mb = round(total_bytes / (1024 * 1024), 2)
                    return VideoDownloadResult(
                        success=True,
                        file_path=saved_images[0],
                        title=title,
                        uploader=author,
                        file_size_mb=file_size_mb,
                        thumbnail_url=saved_images[0],
                        is_audio=False,
                        images=saved_images,
                        is_photo_slideshow=True,
                        music_url=music_url
                    )

            if audio_only:
                media_url = video_info.get('music') or video_info.get('play')
                ext = "mp3"
            else:
                # Prefer 1080p Full HD (hdplay) -> standard play -> wmplay
                media_url = video_info.get('hdplay') or video_info.get('play') or video_info.get('wmplay')
                ext = "mp4"

            if not media_url:
                return VideoDownloadResult(success=False, error_message="No playable media link found.")
                
            video_id = video_info.get('id')
            direct_web_url = f"https://www.tikwm.com/video/media/play/{video_id}.mp4" if video_id else media_url

            title = video_info.get('title') or "TikTok Media"
            author = video_info.get('author', {}).get('nickname') or "TikTok Creator"
            duration = video_info.get('duration')
            thumbnail = video_info.get('origin_cover') or video_info.get('cover')
            
            unique_id = str(uuid.uuid4())[:8]
            target_path = download_folder / f"tiktok_{unique_id}.{ext}"
            
            with client.stream('GET', media_url, headers=headers, follow_redirects=True) as stream_resp:
                if stream_resp.status_code != 200:
                    return VideoDownloadResult(success=False, error_message=f"Failed to stream media (HTTP {stream_resp.status_code})")
                
                downloaded_bytes = 0
                max_bytes = MAX_FILE_SIZE_MB * 1024 * 1024
                
                with open(target_path, 'wb') as f:
                    for chunk in stream_resp.iter_bytes(chunk_size=65536):
                        downloaded_bytes += len(chunk)
                        if downloaded_bytes > max_bytes:
                            target_path.unlink(missing_ok=True)
                            return VideoDownloadResult(
                                success=False,
                                error_message=f"ទំហំឯកសារធំជាង {MAX_FILE_SIZE_MB} MB ដែលលើសពីកម្រិត Telegram Bot អនុញ្ញាត។"
                            )
                        f.write(chunk)
                        
            file_size_mb = round(downloaded_bytes / (1024 * 1024), 2)
            return VideoDownloadResult(
                success=True,
                file_path=str(target_path),
                title=title,
                duration=duration,
                thumbnail_url=thumbnail,
                uploader=author,
                file_size_mb=file_size_mb,
                direct_web_url=direct_web_url,
                is_audio=audio_only
            )
    except Exception as e:
        return VideoDownloadResult(success=False, error_message=f"កំហុសក្នុងការទាញយក TikTok៖ {str(e)[:120]}")

def _get_youtube_cookiefile() -> Optional[str]:
    """Retrieve YouTube cookies from file or environment variable to bypass heavy cloud IP blocks."""
    root_dir = Path(__file__).resolve().parent.parent
    c_path = root_dir / "cookies.txt"
    if c_path.exists():
        return str(c_path)
    if os.getenv("YOUTUBE_COOKIES"):
        tmp = DOWNLOAD_DIR / "cookies.txt"
        try:
            tmp.write_text(os.getenv("YOUTUBE_COOKIES", ""), encoding="utf-8")
            return str(tmp)
        except Exception:
            pass
    return None

YOUTUBE_EXTRACTOR_ARGS = {
    'youtube': {
        'player_client': ['android', 'ios', 'tv_embedded'],
        'player_skip': ['webpage', 'configs']
    }
}

def _sync_download(url: str, download_folder: Path, quality: str = "best", audio_only: bool = False) -> VideoDownloadResult:
    """Internal synchronous worker for downloading video or audio with multi-client bypass."""
    # If TikTok, use dedicated fast watermark-free downloader first
    if is_tiktok_url(url):
        tiktok_res = _download_tiktok_api(url, download_folder, audio_only=audio_only)
        if tiktok_res.success:
            return tiktok_res

    # Pre-fetch authentic metadata via public oEmbed if YouTube
    oembed_info: Optional[Dict[str, str]] = None
    if is_youtube_url(url):
        oembed_info = fetch_youtube_oembed(url)
        o_title = (oembed_info.get("title") if oembed_info else "") or ""
        is_music_content = any(k in o_title.lower() for k in [
            "audio", "song", "music", "mv", "slow", "remix", "beat", "cover", "prod", "lyrics", "ft.", "feat", "official", "remake"
        ]) or any(k in o_title for k in ["បទ", "ចម្រៀង", "ភ្លេង"])

        # Direct fast audio bypass for YouTube music tracks on cloud datacenter IPs
        if (audio_only or is_music_content) and not _get_youtube_cookiefile():
            try:
                from services.music_service import _search_and_download_song_sync
                search_query = clean_song_title(o_title) if o_title else url
                logger.info(f"Direct fast audio fallback for YouTube link: '{search_query}'")
                song_res = _search_and_download_song_sync(search_query, prefer_soundcloud=True)
                if song_res and isinstance(song_res, dict) and song_res.get("file_path") and os.path.exists(song_res["file_path"]):
                    f_size = round(os.path.getsize(song_res["file_path"]) / (1024 * 1024), 2)
                    return VideoDownloadResult(
                        success=True,
                        file_path=song_res["file_path"],
                        title=song_res.get("title") or o_title or "Audio Track",
                        duration=song_res.get("duration"),
                        thumbnail_url=oembed_info.get("thumbnail_url") if oembed_info else song_res.get("thumbnail"),
                        uploader=song_res.get("performer") or (oembed_info.get("author_name") if oembed_info else "YouTube"),
                        file_size_mb=f_size,
                        is_audio=True
                    )
            except Exception as e_fast_audio:
                logger.warning(f"Direct fast audio fallback failed: {e_fast_audio}")

    unique_id = str(uuid.uuid4())[:8]
    output_template = str(download_folder / f"media_{unique_id}_%(id)s.%(ext)s")
    
    # Configure quality format (prioritize 8K / 4K / 1080p within Telegram's 50MB bot upload limit)
    if audio_only:
        fmt = 'bestaudio[ext=m4a]/bestaudio[ext=mp3]/bestaudio/best'
    elif quality == "8k":
        fmt = 'bestvideo[height<=4320][filesize_approx<?48M]+bestaudio/bestvideo[height<=2160][filesize_approx<?48M]+bestaudio/bestvideo[height<=1080][filesize_approx<?48M]+bestaudio/best[filesize_approx<?48M]/best'
    elif quality == "4k":
        fmt = 'bestvideo[height<=2160][filesize_approx<?48M]+bestaudio/bestvideo[height<=1440][filesize_approx<?48M]+bestaudio/bestvideo[height<=1080][filesize_approx<?48M]+bestaudio/best[filesize_approx<?48M]/best'
    elif quality == "1080p":
        fmt = 'bestvideo[height<=1080][filesize_approx<?48M]+bestaudio/bestvideo[height<=720][filesize_approx<?48M]+bestaudio/best[filesize_approx<?48M]/best'
    elif quality == "720p":
        fmt = 'bestvideo[height<=720][filesize_approx<?48M]+bestaudio/best[height<=720][filesize_approx<?48M]/best[height<=720]/best'
    elif quality == "480p":
        fmt = 'bestvideo[height<=480][filesize_approx<?48M]+bestaudio/best[height<=480][filesize_approx<?48M]/best[height<=480]/best'
    else:
        fmt = 'bestvideo[height<=2160][filesize_approx<?48M]+bestaudio/bestvideo[height<=1080][filesize_approx<?48M]+bestaudio/best[height<=1080]/best'

    cookiefile = _get_youtube_cookiefile()

    # Fast client strategy for video downloads
    client_strategies = [
        ['android', 'ios'],
    ]

    last_error: Optional[Exception] = None

    for client_list in client_strategies:
        ydl_opts: Dict[str, Any] = {
            'format': fmt,
            'outtmpl': output_template,
            'noplaylist': True,
            'quiet': True,
            'no_warnings': True,
            'source_address': '0.0.0.0',
            'socket_timeout': 10,
            'retries': 1,
            'fragment_retries': 1,
            'extractor_retries': 1,
            'extractor_args': {
                'youtube': {
                    'player_client': client_list,
                    'player_skip': ['webpage', 'configs']
                }
            },
        }
        
        if cookiefile:
            ydl_opts['cookiefile'] = cookiefile

        if not audio_only:
            ydl_opts['merge_output_format'] = 'mp4'

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                if not info:
                    continue
                
                expected_filename = ydl.prepare_filename(info)
                actual_file = None
                
                base_prefix = f"media_{unique_id}_"
                for f in download_folder.glob(f"{base_prefix}*"):
                    if f.is_file():
                        actual_file = f
                        break
                        
                if not actual_file or not actual_file.exists():
                    if os.path.exists(expected_filename):
                        actual_file = Path(expected_filename)
                
                if not actual_file or not actual_file.exists():
                    continue
                    
                file_bytes = actual_file.stat().st_size
                file_size_mb = round(file_bytes / (1024 * 1024), 2)
                
                if file_size_mb > MAX_FILE_SIZE_MB:
                    try:
                        actual_file.unlink()
                    except Exception:
                        pass
                    return VideoDownloadResult(
                        success=False,
                        file_size_mb=file_size_mb,
                        error_message=f"ទំហំឯកសារ ({file_size_mb} MB) ធំជាងកម្រិត Telegram Bot អនុញ្ញាត ({MAX_FILE_SIZE_MB} MB)។"
                    )
                    
                title = info.get('title') or ("Audio" if audio_only else "Video")
                duration = info.get('duration')
                thumbnail = info.get('thumbnail')
                uploader = info.get('uploader') or info.get('channel') or "Unknown"
                
                return VideoDownloadResult(
                    success=True,
                    file_path=str(actual_file),
                    title=title,
                    duration=duration,
                    thumbnail_url=thumbnail,
                    uploader=uploader,
                    file_size_mb=file_size_mb,
                    is_audio=audio_only
                )
        except Exception as e:
            last_error = e
            # Try format fallback to 'best' if requested format wasn't available
            if "format is not available" in str(e).lower() and fmt != 'best':
                fmt = 'best'
            continue

    # If all client strategies were exhausted
    if last_error:
        err_str = str(last_error)
        err_lower = err_str.lower()
        if is_tiktok_url(url):
            fallback_res = _download_tiktok_api(url, download_folder, audio_only=audio_only)
            if fallback_res.success:
                return fallback_res

        # YouTube Datacenter IP Block / Bot Block handling
        if is_youtube_url(url):
            o_title = (oembed_info.get("title") if oembed_info else "") or ""
            o_author = (oembed_info.get("author_name") if oembed_info else "") or ""
            o_thumb = (oembed_info.get("thumbnail_url") if oembed_info else "") or ""

            is_bot_blocked = any(k in err_lower for k in [
                "failed to extract any player response",
                "bot",
                "sign in",
                "login",
                "confirm you’re not a bot",
                "confirm you're not a bot",
                "unavailable",
                "does not exist"
            ])

            is_music_content = any(k in o_title.lower() for k in [
                "audio", "song", "music", "mv", "slow", "remix", "beat", "cover", "prod", "lyrics", "ft.", "feat", "official"
            ]) or any(k in o_title for k in ["បទ", "ចម្រៀង", "ភ្លេង"])

            # If user wants audio or if title is music content, trigger automated audio stream fallback
            if is_bot_blocked and (audio_only or is_music_content):
                try:
                    from services.music_service import _search_and_download_song_sync
                    search_query = clean_song_title(o_title) if o_title else (o_title or url)
                    logger.info(f"Triggering automated audio stream fallback for blocked YouTube link: '{search_query}'")
                    song_res = _search_and_download_song_sync(search_query, prefer_soundcloud=True)
                    if song_res and isinstance(song_res, dict) and song_res.get("file_path") and os.path.exists(song_res["file_path"]):
                        f_size = round(os.path.getsize(song_res["file_path"]) / (1024 * 1024), 2)
                        return VideoDownloadResult(
                            success=True,
                            file_path=song_res["file_path"],
                            title=song_res.get("title") or o_title or "Audio Track",
                            duration=song_res.get("duration"),
                            thumbnail_url=o_thumb or song_res.get("thumbnail"),
                            uploader=song_res.get("performer") or o_author or "YouTube",
                            file_size_mb=f_size,
                            is_audio=True
                        )
                except Exception as e_m:
                    logger.warning(f"Audio stream fallback failed: {e_m}")

            # If video was requested or audio fallback failed, format informative message with metadata
            if is_bot_blocked:
                title_disp = f"\n🎬 **ចំណងជើង៖** `{o_title}`" if o_title else ""
                author_disp = f"\n👤 **Channel៖** `{o_author}`" if o_author else ""
                msg = (
                    f"⚠️ *ប្រព័ន្ធ YouTube បានរារាំងការទាញយកវីដេអូនៅលើ Cloud Server (YouTube Bot Block)!*{title_disp}{author_disp}\n\n"
                    "💡 _ដោយសារ Cloud Server (Render) ត្រូវបាន YouTube កម្រិត IP លោកអ្នកអាចចុចប៊ូតុងខាងក្រោមដើម្បីទាញយកជា MP3 ឬបើកមើលលើ Browser!_"
                )
                return VideoDownloadResult(
                    success=False,
                    error_message=msg,
                    title=o_title or "YouTube Video",
                    uploader=o_author or "YouTube",
                    thumbnail_url=o_thumb
                )

        if "file is larger than max-filesize" in err_lower:
            msg = f"ឯកសារនេះមានទំហំធំជាង {MAX_FILE_SIZE_MB} MB ដែលលើសពីកម្រិត Telegram Bot អាចផ្ញើបាន។"
        elif "private video" in err_lower or "login" in err_lower or "sign in" in err_lower:
            msg = "វីដេអូនេះជា Private ឬទាមទារការ Login ចូលគណនី YouTube។"
        elif "does not exist" in err_lower or "removed" in err_lower or "video unavailable" in err_lower:
            msg = "វីដេអូនេះមិនមាននៅលើ YouTube ទៀតទេ (ប្រហែលត្រូវបានម្ចាស់លុប Private ឬបិទការចាក់)។"
        elif "failed to extract any player response" in err_lower:
            msg = "ប្រព័ន្ធ YouTube បានរារាំងការតភ្ជាប់ជាបណ្ដោះអាសន្ន (YouTube Bot Block)។ សូមសាកល្បងម្ដងទៀតបន្តិចទៀត។"
        elif "copyright" in err_lower:
            msg = "វីដេអូនេះត្រូវបានបិទដោយសារបញ្ហារក្សាសិទ្ធិ (Copyright Strike)។"
        else:
            clean_err = re.sub(r'https?://[^\s]+', '', err_str)
            clean_err = re.sub(r'please report this issue.*', '', clean_err, flags=re.IGNORECASE).strip()
            clean_err = clean_err.replace("ERROR:", "").replace("[youtube]", "").strip()
            msg = f"កំហុសក្នុងការទាញយក៖ {clean_err[:120]}"
        return VideoDownloadResult(
            success=False,
            error_message=msg,
            title=oembed_info.get("title") if oembed_info else None,
            uploader=oembed_info.get("author_name") if oembed_info else None,
            thumbnail_url=oembed_info.get("thumbnail_url") if oembed_info else None
        )

    return VideoDownloadResult(success=False, error_message="មិនអាចទាញយកព័ត៌មានវីដេអូបានទេ។")

async def download_video_async(url: str, quality: str = "best") -> VideoDownloadResult:
    """Asynchronously download video with chosen quality and hard timeout protection."""
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(_sync_download, url, DOWNLOAD_DIR, quality, False),
            timeout=35.0
        )
    except asyncio.TimeoutError:
        logger.warning(f"download_video_async timed out after 35s for {url}")
        if is_youtube_url(url):
            oembed_info = fetch_youtube_oembed(url)
            o_title = (oembed_info.get("title") if oembed_info else "") or ""
            o_thumb = (oembed_info.get("thumbnail_url") if oembed_info else "") or ""
            o_author = (oembed_info.get("author_name") if oembed_info else "") or "YouTube"
            try:
                from services.music_service import _search_and_download_song_sync
                search_query = clean_song_title(o_title) if o_title else url
                song_res = await asyncio.to_thread(_search_and_download_song_sync, search_query, True)
                if song_res and isinstance(song_res, dict) and song_res.get("file_path") and os.path.exists(song_res["file_path"]):
                    f_size = round(os.path.getsize(song_res["file_path"]) / (1024 * 1024), 2)
                    return VideoDownloadResult(
                        success=True,
                        file_path=song_res["file_path"],
                        title=song_res.get("title") or o_title or "Audio Track",
                        duration=song_res.get("duration"),
                        thumbnail_url=o_thumb or song_res.get("thumbnail"),
                        uploader=song_res.get("performer") or o_author,
                        file_size_mb=f_size,
                        is_audio=True
                    )
            except Exception as e_m:
                logger.warning(f"Timeout music fallback error: {e_m}")

            return VideoDownloadResult(
                success=False,
                error_message="ការទាញយកពី YouTube ចំណាយពេលយូរពេក (Timeout) ដោយសារប្រព័ន្ធ YouTube កម្រិតល្បឿន Server។ សូមទាញយកជា MP3 ជំនួសវិញ!",
                title=o_title or "YouTube Video",
                uploader=o_author,
                thumbnail_url=o_thumb
            )
        return VideoDownloadResult(
            success=False,
            error_message="ការទាញយកចំណាយពេលយូរពេក (Timeout លើសពី 35 វិនាទី)។ សូមសាកល្បងម្តងទៀត!"
        )

async def download_audio_async(url: str) -> VideoDownloadResult:
    """Asynchronously extract and download audio/mp3 with timeout protection."""
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(_sync_download, url, DOWNLOAD_DIR, "best", True),
            timeout=35.0
        )
    except asyncio.TimeoutError:
        logger.warning(f"download_audio_async timed out after 35s for {url}")
        if is_youtube_url(url):
            oembed_info = fetch_youtube_oembed(url)
            o_title = (oembed_info.get("title") if oembed_info else "") or ""
            o_thumb = (oembed_info.get("thumbnail_url") if oembed_info else "") or ""
            o_author = (oembed_info.get("author_name") if oembed_info else "") or "YouTube"
            try:
                from services.music_service import _search_and_download_song_sync
                search_query = clean_song_title(o_title) if o_title else url
                song_res = await asyncio.to_thread(_search_and_download_song_sync, search_query, True)
                if song_res and isinstance(song_res, dict) and song_res.get("file_path") and os.path.exists(song_res["file_path"]):
                    f_size = round(os.path.getsize(song_res["file_path"]) / (1024 * 1024), 2)
                    return VideoDownloadResult(
                        success=True,
                        file_path=song_res["file_path"],
                        title=song_res.get("title") or o_title or "Audio Track",
                        duration=song_res.get("duration"),
                        thumbnail_url=o_thumb or song_res.get("thumbnail"),
                        uploader=song_res.get("performer") or o_author,
                        file_size_mb=f_size,
                        is_audio=True
                    )
            except Exception as e_m:
                logger.warning(f"Timeout audio fallback error: {e_m}")
        return VideoDownloadResult(
            success=False,
            error_message="ការទាញយកសំឡេងចំណាយពេលយូរពេក (Timeout)។"
        )

def _sync_download_thumbnail(url: str, download_folder: Path) -> Optional[str]:
    """Download highest resolution thumbnail / cover image."""
    try:
        # Check TikTok first
        if is_tiktok_url(url):
            with httpx.Client(timeout=15) as client:
                resp = client.post('https://www.tikwm.com/api/', data={'url': url})
                if resp.status_code == 200:
                    data = resp.json().get('data', {})
                    cover_url = data.get('origin_cover') or data.get('cover')
                    if cover_url:
                        img_resp = client.get(cover_url, follow_redirects=True)
                        if img_resp.status_code == 200:
                            path = download_folder / f"thumb_{uuid.uuid4().hex[:8]}.jpg"
                            path.write_bytes(img_resp.content)
                            return str(path)

        # yt-dlp thumbnail extraction
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'skip_download': True,
            'source_address': '0.0.0.0',
            'extractor_args': YOUTUBE_EXTRACTOR_ARGS,
        }
        cookiefile = _get_youtube_cookiefile()
        if cookiefile:
            ydl_opts['cookiefile'] = cookiefile
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if not info:
                return None
                
            thumbnails = info.get('thumbnails', [])
            best_thumb_url = None
            if thumbnails:
                # Pick thumbnail with highest resolution / preference
                valid_thumbs = [t for t in thumbnails if t.get('url')]
                if valid_thumbs:
                    best_thumb = max(valid_thumbs, key=lambda t: (t.get('height') or 0, t.get('preference') or 0))
                    best_thumb_url = best_thumb.get('url')
                    
            if not best_thumb_url:
                best_thumb_url = info.get('thumbnail')
                
            if best_thumb_url:
                with httpx.Client(timeout=15) as client:
                    img_resp = client.get(best_thumb_url, follow_redirects=True)
                    if img_resp.status_code == 200:
                        path = download_folder / f"thumb_{uuid.uuid4().hex[:8]}.jpg"
                        path.write_bytes(img_resp.content)
                        return str(path)
    except Exception:
        pass
    return None

async def download_thumbnail_hd(url: str) -> Optional[str]:
    """Asynchronously download high definition thumbnail/cover image."""
    return await asyncio.to_thread(_sync_download_thumbnail, url, DOWNLOAD_DIR)

def cleanup_file(file_path: Optional[str]):
    """Safely delete downloaded temporary file."""
    if file_path and os.path.exists(file_path):
        try:
            os.remove(file_path)
        except Exception:
            pass
