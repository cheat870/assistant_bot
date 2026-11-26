import os
import re
import uuid
import asyncio
import logging
from typing import Dict, Any, List, Optional
import yt_dlp

from config import DOWNLOAD_DIR, MUSIC_CHANNEL_ID
from services.video_downloader import download_audio_async, cleanup_file
from services.music_archive_service import archive_song_to_channel

logger = logging.getLogger(__name__)

def extract_playlist_info(playlist_url: str, max_items: int = 15) -> Dict[str, Any]:
    """Extract list of video entries from a YouTube playlist."""
    ydl_opts = {
        'extract_flat': True,
        'quiet': True,
        'no_warnings': True,
        'playlist_items': f"1-{max_items}",
        'source_address': '0.0.0.0',
        'extractor_args': {
            'youtube': {
                'player_client': ['android', 'ios', 'tv_embedded'],
                'player_skip': ['webpage', 'configs']
            }
        }
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(playlist_url, download=False)
            if not info:
                return {"success": False, "error": "មិនអាចទាញយកព័ត៌មាន Playlist បានទេ"}

            title = info.get("title", "Playlist")
            entries = info.get("entries", [])
            valid_items = []
            for e in entries:
                if not e:
                    continue
                v_id = e.get("id")
                v_url = e.get("url") or (f"https://www.youtube.com/watch?v={v_id}" if v_id else None)
                if v_url:
                    valid_items.append({
                        "id": v_id,
                        "title": e.get("title", "Unknown Title"),
                        "uploader": e.get("uploader", "Unknown Artist"),
                        "url": v_url,
                        "duration": e.get("duration", 0)
                    })

            return {
                "success": True,
                "title": title,
                "items": valid_items[:max_items],
                "total": len(valid_items[:max_items])
            }
    except Exception as e:
        logger.error(f"Error extracting playlist: {e}")
        return {"success": False, "error": str(e)[:120]}

async def process_and_archive_playlist(
    bot,
    chat_id: int,
    user,
    playlist_url: str,
    status_msg,
    max_items: int = 10
) -> Dict[str, Any]:
    """
    Download playlist tracks one by one, send to chat and archive directly to channel @Song182.
    """
    info = extract_playlist_info(playlist_url, max_items=max_items)
    if not info.get("success") or not info.get("items"):
        return {"success": False, "error": info.get("error", "រកមិនឃើញបទចម្រៀងក្នុង Playlist ឡើយ")}

    items = info["items"]
    total = len(items)
    success_count = 0

    await status_msg.edit_text(
        f"🎧 *[Playlist Batch Downloader]* 🎶\n"
        f"📁 Playlist: *{info['title'][:50]}*\n"
        f"🔢 ចំនួនសរុប: *{total} បទ*\n\n"
        f"🚀 *កំពុងចាប់ផ្ដើមទាញយក និង Upload ទៅ Channel @Song182...*",
        parse_mode="Markdown"
    )

    for idx, item in enumerate(items, 1):
        try:
            await status_msg.edit_text(
                f"🎧 *[Playlist Batch Downloader]* 🎶\n"
                f"📁 Playlist: *{info['title'][:40]}*\n"
                f"⏳ *[{idx}/{total}]* កំពុងទាញយក: `{item['title'][:45]}`...\n"
                f"📻 បញ្ជូនទៅ Channel: `@Song182`",
                parse_mode="Markdown"
            )

            res = await download_audio_async(item["url"])
            if res.success and res.file_path and os.path.exists(res.file_path):
                # Send to chat
                with open(res.file_path, "rb") as audio_f:
                    sent_audio = await bot.send_audio(
                        chat_id=chat_id,
                        audio=audio_f,
                        title=res.title,
                        performer=res.uploader,
                        duration=res.duration,
                        caption=f"🎵 {res.title}\n👤 {res.uploader}\n✨ Playlist: {info['title'][:35]}",
                        read_timeout=600.0,
                    )

                # Archive to channel
                if sent_audio and sent_audio.audio:
                    try:
                        dur_sec = res.duration or 0
                        await archive_song_to_channel(
                            bot=bot,
                            user=user,
                            song_data={
                                "title": res.title,
                                "performer": res.uploader,
                                "duration": dur_sec,
                                "duration_str": f"{dur_sec // 60}:{dur_sec % 60:02d}" if dur_sec else "N/A",
                                "query": item["url"],
                            },
                            sent_audio_file_id=sent_audio.audio.file_id
                        )
                    except Exception as e_arch:
                        logger.warning(f"Archive playlist track failed: {e_arch}")

                cleanup_file(res.file_path)
                success_count += 1
            else:
                logger.warning(f"Failed track: {item['title']} - {res.error_message}")

        except Exception as e_track:
            logger.error(f"Error processing playlist track {idx}: {e_track}")

        # Sleep briefly between items to respect Telegram rate limits
        await asyncio.sleep(2)

    await status_msg.edit_text(
        f"✅ *ទាញយក Playlist បានសម្រេច!* 🎉\n\n"
        f"📁 Playlist: *{info['title'][:50]}*\n"
        f"🎉 បាន Upload ជោគជ័យ: *{success_count}/{total} បទ*\n"
        f"📻 បានរក្សាទុកក្នុង Channel: `@Song182` រួចរាល់!",
        parse_mode="Markdown"
    )

    return {"success": True, "total": total, "completed": success_count}
