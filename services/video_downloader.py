import os
import re
import uuid
import asyncio
from pathlib import Path
from typing import Optional, Dict, Any, List
import httpx
import yt_dlp

from config import DOWNLOAD_DIR, MAX_FILE_SIZE_MB

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

def _sync_download(url: str, download_folder: Path, quality: str = "best", audio_only: bool = False) -> VideoDownloadResult:
    """Internal synchronous worker for downloading video or audio."""
    # If TikTok, use dedicated fast watermark-free downloader first
    if is_tiktok_url(url):
        tiktok_res = _download_tiktok_api(url, download_folder, audio_only=audio_only)
        if tiktok_res.success:
            return tiktok_res

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

    ydl_opts: Dict[str, Any] = {
        'format': fmt,
        'outtmpl': output_template,
        'noplaylist': True,
        'quiet': True,
        'no_warnings': True,
        'source_address': '0.0.0.0',
        'socket_timeout': 30,
        'max_filesize': MAX_FILE_SIZE_MB * 1024 * 1024,
        'js_runtimes': {'node': {}},
        'extractor_args': {
            'youtube': {
                'player_client': ['tv', 'web_embedded', 'android'],
                'player_skip': ['webpage']
            }
        },
    }
    
    if not audio_only:
        ydl_opts['merge_output_format'] = 'mp4'

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if not info:
                return VideoDownloadResult(success=False, error_message="មិនអាចទាញយកព័ត៌មានវីដេអូបានទេ។")
            
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
                return VideoDownloadResult(success=False, error_message="ឯកសារត្រូវបានទាញយកតែរកមិនឃើញ។")
                
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
            
    except yt_dlp.utils.DownloadError as e:
        err_str = str(e)
        if is_tiktok_url(url):
            fallback_res = _download_tiktok_api(url, download_folder, audio_only=audio_only)
            if fallback_res.success:
                return fallback_res
                
        if "File is larger than max-filesize" in err_str:
            msg = f"ឯកសារនេះមានទំហំធំជាង {MAX_FILE_SIZE_MB} MB ដែលលើសពីកម្រិត Telegram Bot អាចផ្ញើបាន។"
        elif "Private video" in err_str or "login" in err_str.lower():
            msg = "វីដេអូនេះជា Private ឬទាមទារ Login ចូលគណនី។"
        else:
            msg = f"កំហុសក្នុងការទាញយក៖ {err_str[:120]}"
        return VideoDownloadResult(success=False, error_message=msg)
    except Exception as e:
        return VideoDownloadResult(success=False, error_message=f"កំហុសបច្ចេកទេស៖ {str(e)[:120]}")

async def download_video_async(url: str, quality: str = "best") -> VideoDownloadResult:
    """Asynchronously download video with chosen quality."""
    return await asyncio.to_thread(_sync_download, url, DOWNLOAD_DIR, quality, False)

async def download_audio_async(url: str) -> VideoDownloadResult:
    """Asynchronously extract and download audio/mp3."""
    return await asyncio.to_thread(_sync_download, url, DOWNLOAD_DIR, "best", True)

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
        ydl_opts = {'quiet': True, 'no_warnings': True, 'skip_download': True}
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
