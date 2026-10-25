import os
import re
import uuid
import asyncio
from pathlib import Path
from typing import Optional, Dict, Any
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
        error_message: Optional[str] = None
    ):
        self.success = success
        self.file_path = file_path
        self.title = title or "Video"
        self.duration = duration
        self.thumbnail_url = thumbnail_url
        self.uploader = uploader or "Unknown"
        self.file_size_mb = file_size_mb
        self.direct_web_url = direct_web_url
        self.error_message = error_message

def _download_tiktok_api(url: str, download_folder: Path) -> VideoDownloadResult:
    """High-speed watermark-free TikTok downloader via dedicated API."""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        }
        with httpx.Client(timeout=30) as client:
            resp = client.post('https://www.tikwm.com/api/', data={'url': url})
            if resp.status_code != 200:
                return VideoDownloadResult(success=False, error_message="Failed to contact TikTok API service.")
            
            data = resp.json()
            if data.get('code') != 0:
                err_msg = data.get('msg', 'Unknown TikTok error')
                return VideoDownloadResult(success=False, error_message=f"TikTok Error: {err_msg}")
            
            video_info = data.get('data', {})
            # Prefer standard play (no watermark) or hdplay
            play_url = video_info.get('play') or video_info.get('hdplay') or video_info.get('wmplay')
            if not play_url:
                return VideoDownloadResult(success=False, error_message="No playable video link found.")
                
            video_id = video_info.get('id')
            direct_web_url = f"https://www.tikwm.com/video/media/play/{video_id}.mp4" if video_id else play_url

            title = video_info.get('title') or "TikTok Video"
            author = video_info.get('author', {}).get('nickname') or "TikTok Creator"
            duration = video_info.get('duration')
            thumbnail = video_info.get('cover')
            
            unique_id = str(uuid.uuid4())[:8]
            target_path = download_folder / f"tiktok_{unique_id}.mp4"
            
            with client.stream('GET', play_url, headers=headers, follow_redirects=True) as stream_resp:
                if stream_resp.status_code != 200:
                    return VideoDownloadResult(success=False, error_message=f"Failed to stream video (HTTP {stream_resp.status_code})")
                
                downloaded_bytes = 0
                max_bytes = MAX_FILE_SIZE_MB * 1024 * 1024
                
                with open(target_path, 'wb') as f:
                    for chunk in stream_resp.iter_bytes(chunk_size=65536):
                        downloaded_bytes += len(chunk)
                        if downloaded_bytes > max_bytes:
                            target_path.unlink(missing_ok=True)
                            return VideoDownloadResult(
                                success=False,
                                error_message=f"ទំហំវីដេអូធំជាង {MAX_FILE_SIZE_MB} MB ដែលលើសពីកម្រិត Telegram Bot អនុញ្ញាត។"
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
                direct_web_url=direct_web_url
            )
    except Exception as e:
        return VideoDownloadResult(success=False, error_message=f"កំហុសក្នុងការទាញយក TikTok៖ {str(e)[:120]}")

def _sync_download(url: str, download_folder: Path) -> VideoDownloadResult:
    """Internal synchronous worker for video downloading."""
    # If TikTok, use dedicated fast watermark-free downloader first
    if is_tiktok_url(url):
        tiktok_res = _download_tiktok_api(url, download_folder)
        if tiktok_res.success:
            return tiktok_res

    # Use yt-dlp for all other sites (YouTube, Facebook, Instagram, Twitter/X, etc.)
    unique_id = str(uuid.uuid4())[:8]
    output_template = str(download_folder / f"vid_{unique_id}_%(id)s.%(ext)s")
    
    ydl_opts: Dict[str, Any] = {
        'format': 'best[filesize<48M]/bestvideo[filesize<40M]+bestaudio/best[ext=mp4]/best',
        'outtmpl': output_template,
        'noplaylist': True,
        'quiet': True,
        'no_warnings': True,
        'merge_output_format': 'mp4',
        'socket_timeout': 30,
        'max_filesize': MAX_FILE_SIZE_MB * 1024 * 1024,
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if not info:
                return VideoDownloadResult(success=False, error_message="មិនអាចទាញយកព័ត៌មានវីដេអូបានទេ។")
            
            expected_filename = ydl.prepare_filename(info)
            actual_file = None
            
            base_prefix = f"vid_{unique_id}_"
            for f in download_folder.glob(f"{base_prefix}*"):
                if f.is_file():
                    actual_file = f
                    break
                    
            if not actual_file or not actual_file.exists():
                if os.path.exists(expected_filename):
                    actual_file = Path(expected_filename)
            
            if not actual_file or not actual_file.exists():
                return VideoDownloadResult(success=False, error_message="ឯកសារវីដេអូត្រូវបានទាញយកតែរកមិនឃើញ។")
                
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
                    error_message=f"ទំហំវីដេអូ ({file_size_mb} MB) ធំជាងកម្រិត Telegram Bot អនុញ្ញាត ({MAX_FILE_SIZE_MB} MB)។"
                )
                
            title = info.get('title') or "Video"
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
                file_size_mb=file_size_mb
            )
            
    except yt_dlp.utils.DownloadError as e:
        err_str = str(e)
        # If it was a TikTok link and yt-dlp failed, try TikTok API fallback as secondary attempt
        if is_tiktok_url(url):
            fallback_res = _download_tiktok_api(url, download_folder)
            if fallback_res.success:
                return fallback_res
                
        if "File is larger than max-filesize" in err_str:
            msg = f"វីដេអូនេះមានទំហំធំជាង {MAX_FILE_SIZE_MB} MB ដែលលើសពីកម្រិត Telegram Bot អាចផ្ញើបាន។"
        elif "Private video" in err_str or "login" in err_str.lower():
            msg = "វីដេអូនេះជា Private ឬទាមទារ Login ចូលគណនី។"
        else:
            msg = f"កំហុសក្នុងការទាញយក៖ {err_str[:120]}"
        return VideoDownloadResult(success=False, error_message=msg)
    except Exception as e:
        return VideoDownloadResult(success=False, error_message=f"កំហុសបច្ចេកទេស៖ {str(e)[:120]}")

async def download_video_async(url: str) -> VideoDownloadResult:
    """Asynchronously download video using thread pool."""
    return await asyncio.to_thread(_sync_download, url, DOWNLOAD_DIR)

def cleanup_file(file_path: Optional[str]):
    """Safely delete downloaded temporary file."""
    if file_path and os.path.exists(file_path):
        try:
            os.remove(file_path)
        except Exception:
            pass
