import html
import logging
from typing import Optional, Dict, Any, Tuple
from telegram import InlineKeyboardMarkup, InlineKeyboardButton
from database import get_music_channel, log_music_archive

logger = logging.getLogger(__name__)

async def verify_channel_access(bot, channel_target: str) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    """
    Verify if bot can access the channel and check administrator permissions.
    Returns: (is_accessible, error_message, chat_info_dict)
    """
    if not channel_target or not channel_target.strip():
        return False, "សូមបញ្ជាក់ Username ឬ ID របស់ Channel (ឧទាហរណ៍៖ @mychannel ឬ -100xxxxxxxxxx)", None

    target = channel_target.strip()
    try:
        bot_id = int(bot.token.split(":")[0]) if hasattr(bot, "token") and bot.token else (bot.id if hasattr(bot, "id") else None)
        if not bot_id and hasattr(bot, "get_me"):
            me = await bot.get_me()
            bot_id = me.id
        chat = await bot.get_chat(target)
        try:
            bot_member = await bot.get_chat_member(chat.id, bot_id)
            is_admin = bot_member.status in ["administrator", "creator"]
            can_post = getattr(bot_member, "can_post_messages", None)
            if can_post is None:
                can_post = is_admin
        except Exception:
            is_admin = False
            can_post = False

        return True, "", {
            "id": chat.id,
            "title": chat.title or str(chat.id),
            "username": chat.username,
            "type": chat.type,
            "is_admin": is_admin,
            "can_post": can_post,
        }
    except Exception as e:
        err_msg = str(e)
        logger.warning(f"Failed to access channel '{target}': {err_msg}")
        return False, err_msg, None

async def archive_song_to_channel(
    bot,
    user,
    song_data: Dict[str, Any],
    sent_audio_file_id: str
) -> Optional[Dict[str, Any]]:
    """
    Instantly archive the downloaded song into the configured music storage channel.
    Uses Telegram's cached audio file_id for 0.1-second instantaneous zero-bandwidth posting.
    """
    channel_target = get_music_channel() or "-1003994142170"
    if not channel_target:
        return None

    try:
        title = song_data.get("title", "Unknown Title")
        performer = song_data.get("performer", "Unknown Artist")
        duration_str = song_data.get("duration_str", "Unknown")
        dur_sec = int(song_data.get("duration", 0) or 0)
        query = song_data.get("query", title)

        # Build clean user credit
        if user and getattr(user, "username", None):
            user_credit = f"@{user.username}"
        elif user and getattr(user, "first_name", None):
            user_credit = user.first_name
        else:
            user_credit = "អ្នកប្រើប្រាស់ (User)"

        bot_username = getattr(bot, "username", "assistant_bot") or "assistant_bot"

        # Channel post caption with safe HTML escaping (prevents underscore/bracket Markdown parsing crashes)
        channel_caption = (
            f"🎧 <b>{html.escape(title)}</b>\n"
            f"👤 <b>តារាចម្រៀង (Artist):</b> {html.escape(performer)}\n"
            f"⏱️ <b>រយៈពេល (Duration):</b> {duration_str}\n"
            f"🔎 <b>សំណើដោយ (Requested by):</b> {html.escape(user_credit)}\n\n"
            f"✨ <b>ស្តាប់ &amp; ទាញយកចម្រៀងឥតគិតថ្លៃ:</b> @{html.escape(bot_username)}\n"
            f"🎵 <b>Smart Assistant Music Archive</b>"
        )

        channel_markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("🎧 ស្នើសុំបទចម្រៀង (Request Song)", url=f"https://t.me/{bot_username}?start=song")]
        ])

        try:
            channel_msg = await bot.send_audio(
                chat_id=channel_target,
                audio=sent_audio_file_id,
                title=title,
                performer=performer,
                duration=dur_sec,
                caption=channel_caption,
                parse_mode="HTML",
                reply_markup=channel_markup
            )
        except Exception as e_html:
            logger.warning(f"HTML send_audio failed, retrying plain text: {e_html}")
            # Fallback without formatting if HTML still fails
            channel_msg = await bot.send_audio(
                chat_id=channel_target,
                audio=sent_audio_file_id,
                title=title,
                performer=performer,
                duration=dur_sec,
                caption=f"🎧 {title}\n👤 {performer}\n⏱️ {duration_str}\n🔎 {user_credit}\n\n✨ @{bot_username}",
                reply_markup=channel_markup
            )

        chat_obj = channel_msg.chat
        post_url = None
        if chat_obj and chat_obj.username:
            post_url = f"https://t.me/{chat_obj.username}/{channel_msg.message_id}"
        elif channel_target.startswith("@"):
            post_url = f"https://t.me/{channel_target.lstrip('@')}/{channel_msg.message_id}"

        # Record in SQLite archive log
        user_id = getattr(user, "id", 0) if user else 0
        log_music_archive(
            chat_id=user_id,
            query=query,
            title=title,
            performer=performer,
            duration=dur_sec,
            file_id=sent_audio_file_id,
            channel_id=channel_target,
            channel_message_id=channel_msg.message_id
        )

        return {
            "success": True,
            "channel_id": channel_target,
            "channel_title": chat_obj.title if chat_obj else channel_target,
            "message_id": channel_msg.message_id,
            "post_url": post_url
        }

    except Exception as e:
        logger.warning(f"Could not archive song to channel {channel_target}: {e}")
        return {
            "success": False,
            "channel_id": channel_target,
            "error": str(e)
        }

async def archive_video_to_channel(
    bot,
    user,
    video_data: Dict[str, Any],
    sent_video_file_id: str
) -> Optional[Dict[str, Any]]:
    """
    Instantly archive the downloaded video into the configured storage channel (@Song182).
    Uses Telegram's cached video file_id for 0.1-second instantaneous zero-bandwidth posting.
    """
    channel_target = get_music_channel() or "-1003994142170"
    if not channel_target:
        return None

    try:
        title = video_data.get("title", "Unknown Title")
        uploader = video_data.get("uploader", "Unknown Creator")
        duration = video_data.get("duration", 0)
        dur_sec = int(duration) if duration else 0
        dur_str = f"{dur_sec // 60}:{dur_sec % 60:02d}" if dur_sec else ""
        url = video_data.get("url", "")

        # Build clean user credit
        if user and getattr(user, "username", None):
            user_credit = f"@{user.username}"
        elif user and getattr(user, "first_name", None):
            user_credit = user.first_name
        else:
            user_credit = "អ្នកប្រើប្រាស់ (User)"

        bot_username = getattr(bot, "username", "Researchmap_bot") or "Researchmap_bot"

        dur_line = f"⏱️ <b>រយៈពេល (Duration):</b> {dur_str}\n" if dur_str else ""
        channel_caption = (
            f"🎬 <b>{html.escape(title[:120])}</b>\n"
            f"👤 <b>អ្នកបង្កើត (Creator):</b> {html.escape(uploader[:50])}\n"
            f"{dur_line}"
            f"🔎 <b>សំណើដោយ (Requested by):</b> {html.escape(user_credit)}\n\n"
            f"✨ <b>ទាញយកវីដេអូ &amp; ចម្រៀងឥតគិតថ្លៃ:</b> @{html.escape(bot_username)}\n"
            f"🎵 <b>Smart Assistant Media Hub</b>"
        )

        channel_markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("🎬 ទាញយកវីដេអូ / ចម្រៀង", url=f"https://t.me/{bot_username}?start=dl")]
        ])

        try:
            channel_msg = await bot.send_video(
                chat_id=channel_target,
                video=sent_video_file_id,
                caption=channel_caption,
                parse_mode="HTML",
                supports_streaming=True,
                reply_markup=channel_markup
            )
        except Exception as e_html:
            logger.warning(f"HTML send_video to channel failed, retrying plain text: {e_html}")
            channel_msg = await bot.send_video(
                chat_id=channel_target,
                video=sent_video_file_id,
                caption=f"🎬 {title[:120]}\n👤 {uploader[:50]}\n🔎 {user_credit}\n\n✨ @{bot_username}",
                supports_streaming=True,
                reply_markup=channel_markup
            )

        chat_obj = channel_msg.chat
        post_url = None
        if chat_obj and chat_obj.username:
            post_url = f"https://t.me/{chat_obj.username}/{channel_msg.message_id}"
        elif channel_target.startswith("@"):
            post_url = f"https://t.me/{channel_target.lstrip('@')}/{channel_msg.message_id}"

        # Record in SQLite archive log
        user_id = getattr(user, "id", 0) if user else 0
        log_music_archive(
            chat_id=user_id,
            query=url or title,
            title=title,
            performer=uploader,
            duration=dur_sec,
            file_id=sent_video_file_id,
            channel_id=channel_target,
            channel_message_id=channel_msg.message_id
        )

        return {
            "success": True,
            "channel_id": channel_target,
            "channel_title": chat_obj.title if chat_obj else channel_target,
            "message_id": channel_msg.message_id,
            "post_url": post_url
        }
    except Exception as e:
        logger.warning(f"Could not archive video to channel {channel_target}: {e}")
        return {
            "success": False,
            "channel_id": channel_target,
            "error": str(e)
        }

async def archive_photos_to_channel(
    bot,
    user,
    photo_data: Dict[str, Any],
    sent_photo_file_ids: list
) -> Optional[Dict[str, Any]]:
    """
    Instantly archive downloaded Photo Slideshow / Live Photos into the storage channel (@Song182).
    Uses Telegram's cached photo file_ids for instant zero-bandwidth posting.
    """
    channel_target = get_music_channel() or "-1003994142170"
    if not channel_target or not sent_photo_file_ids:
        return None

    try:
        from telegram import InputMediaPhoto
        title = photo_data.get("title", "TikTok Photos")
        uploader = photo_data.get("uploader", "TikTok Creator")

        # Build clean user credit
        if user and getattr(user, "username", None):
            user_credit = f"@{user.username}"
        elif user and getattr(user, "first_name", None):
            user_credit = user.first_name
        else:
            user_credit = "អ្នកប្រើប្រាស់ (User)"

        bot_username = getattr(bot, "username", "Researchmap_bot") or "Researchmap_bot"

        caption = (
            f"📸 <b>{html.escape(title[:120])}</b>\n"
            f"🖼️ <b>ចំនួនរូបថត (HD Photos):</b> {len(sent_photo_file_ids)} សន្លឹក\n"
            f"👤 <b>អ្នកបង្កើត (Creator):</b> {html.escape(uploader[:50])}\n"
            f"🔎 <b>សំណើដោយ (Requested by):</b> {html.escape(user_credit)}\n\n"
            f"✨ <b>ទាញយករូបថត &amp; ចម្រៀងឥតគិតថ្លៃ:</b> @{html.escape(bot_username)}\n"
            f"🎵 <b>Smart Assistant Media Hub</b>"
        )

        media = []
        for i, fid in enumerate(sent_photo_file_ids[:10]):
            cap = caption if i == 0 else None
            media.append(InputMediaPhoto(media=fid, caption=cap, parse_mode="HTML"))

        await bot.send_media_group(chat_id=channel_target, media=media)
        return {"success": True, "channel_id": channel_target}
    except Exception as e:
        logger.warning(f"Could not archive photos to channel {channel_target}: {e}")
        return {"success": False, "channel_id": channel_target, "error": str(e)}
