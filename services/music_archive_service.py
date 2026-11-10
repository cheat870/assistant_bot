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
        chat = await bot.get_chat(target)
        try:
            bot_member = await bot.get_chat_member(chat.id, bot.id)
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
    channel_target = get_music_channel()
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

        # Channel post caption
        channel_caption = (
            f"🎧 *{title}*\n"
            f"👤 *តារាចម្រៀង (Artist):* {performer}\n"
            f"⏱️ *រយៈពេល (Duration):* {duration_str}\n"
            f"🔎 *សំណើដោយ (Requested by):* {user_credit}\n\n"
            f"✨ *ស្តាប់ & ទាញយកចម្រៀងឥតគិតថ្លៃ:* @{bot_username}\n"
            f"🎵 *Smart Assistant Music Archive*"
        )

        channel_markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("🎧 ស្នើសុំបទចម្រៀង (Request Song)", url=f"https://t.me/{bot_username}?start=song")]
        ])

        channel_msg = await bot.send_audio(
            chat_id=channel_target,
            audio=sent_audio_file_id,
            title=title,
            performer=performer,
            duration=dur_sec,
            caption=channel_caption,
            parse_mode="Markdown",
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
