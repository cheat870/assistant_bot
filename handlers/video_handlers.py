import os
import uuid
import asyncio
import logging
from typing import Dict
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from services.video_downloader import (
    extract_video_url,
    download_video_async,
    download_audio_async,
    download_thumbnail_hd,
    cleanup_file,
)
from database import log_download, is_ai_mode
from services.ai_service import query_continuous_ai
from handlers.command_handlers import (
    get_main_menu_keyboard,
    start_command,
    weather_command,
    calendar_command,
    finance_command,
    reminders_command,
    aimode_command,
)

logger = logging.getLogger(__name__)

# Temporary in-memory cache for media tokens (token -> URL)
URL_TOKEN_CACHE: Dict[str, str] = {}

def get_or_create_media_token(url: str) -> str:
    """Map URL to a short token for callback data (max 64 bytes in Telegram)."""
    # Keep cache from growing unboundedly
    if len(URL_TOKEN_CACHE) > 500:
        # Remove first 100 entries
        keys = list(URL_TOKEN_CACHE.keys())[:100]
        for k in keys:
            URL_TOKEN_CACHE.pop(k, None)
            
    for token, cached_url in URL_TOKEN_CACHE.items():
        if cached_url == url:
            return token
            
    token = uuid.uuid4().hex[:10]
    URL_TOKEN_CACHE[token] = url
    return token

async def handle_video_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Detect and process video download requests or AI Continuous Chat."""
    text = update.message.text
    if not text:
        return
        
    chat = update.effective_chat

    # Quick routing for persistent bottom keyboard buttons
    if text == "🏠 ផ្ទាំង Menu មេ":
        await start_command(update, context)
        return
    elif text == "🌤️ អាកាសធាតុ":
        await weather_command(update, context)
        return
    elif text == "🗓️ ប្រតិទិនបុណ្យជាតិ":
        await calendar_command(update, context)
        return
    elif text == "💰 សេដ្ឋកិច្ច/មាស/សាំង":
        await finance_command(update, context)
        return
    elif text == "⏰ Reminders":
        await reminders_command(update, context)
        return
    elif text == "✨ AI Chat":
        await aimode_command(update, context)
        return
    elif text == "📥 របៀបទាញយក":
        help_msg = (
            "📥 *របៀបទាញយកវីដេអូ & MP3 & Cover HD៖*\n\n"
            "1. ចូលទៅកាន់ TikTok, YouTube, Facebook, Instagram ឬ X/Twitter\n"
            "2. ចុចពាក្យ **Share** រួចជ្រើសរើស **Copy Link**\n"
            "3. ផ្ញើ (Paste) Link ចូលក្នុង Bot នេះភ្លាមៗ\n"
            "4. Bot នឹងទាញយកវីដេអូ និងមានជម្រើសសម្រាប់ទាញយក MP3 ឬ Cover HD ដោយស្វ័យប្រវត្ត!"
        )
        await update.message.reply_text(help_msg, parse_mode="Markdown")
        return

    url = extract_video_url(text)
    
    # If not a URL, check if continuous AI mode is active
    if not url:
        if is_ai_mode(chat.id):
            await chat.send_action("typing")
            ai_reply = await query_continuous_ai(chat.id, text)
            exit_button = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔕 បិទ AI Mode", callback_data="btn_toggle_aimode")]
            ])
            await update.message.reply_text(ai_reply, reply_markup=exit_button, parse_mode="Markdown")
            return
            
        reply_msg = (
            "🤖 ខ្ញុំពុំទាន់ឃើញមាន Link វីដេអូនៅឡើយទេ។\n\n"
            "👉 សូមផ្ញើ Link ពី **TikTok, YouTube, Facebook, Instagram ឬ X** ដើម្បីឱ្យខ្ញុំទាញយកវីដេអូជូន\n"
            "ឬចុច Menu ខាងក្រោមដើម្បីប្រើមុខងារផ្សេងៗ៖"
        )
        await update.message.reply_text(
            reply_msg,
            reply_markup=get_main_menu_keyboard(chat.id),
            parse_mode="Markdown"
        )
        return
        
    token = get_or_create_media_token(url)
    
    # Send initial status
    status_msg = await update.message.reply_text(
        "⏳ *កំពុងដំណើរការទាញយកវីដេអូ...*\n"
        "🔗 ប្រភព: `កំពុងទាញយកទិន្នន័យ...`\n"
        "សូមរង់ចាំបន្តិចណា៎! 🚀",
        parse_mode="Markdown"
    )
    
    await chat.send_action("record_video")
    
    # Download the video asynchronously
    result = await download_video_async(url)
    
    if not result.success:
        err_text = f"❌ *ការទាញយកមិនបានសម្រេច!*\n\n{result.error_message}"
        try:
            await status_msg.edit_text(err_text, parse_mode="Markdown")
        except Exception:
            await update.message.reply_text(err_text, parse_mode="Markdown")
        return
        
    # Build buttons for MP3, HD Cover, and direct web link
    buttons = [
        [
            InlineKeyboardButton("🎵 ទាញយកជា MP3", callback_data=f"dlmp3_{token}"),
            InlineKeyboardButton("🖼️ រូប Cover HD", callback_data=f"dlthumb_{token}"),
        ]
    ]
    if result.direct_web_url:
        buttons.append([InlineKeyboardButton("⚡ មើល / Download ផ្ទាល់ (No Wait)", url=result.direct_web_url)])
    reply_markup = InlineKeyboardMarkup(buttons)

    # Send uploading status
    try:
        await status_msg.edit_text(
            f"📤 *ទាញយកជោគជ័យ!* កំពុង Upload វីដេអូទៅ Telegram...\n"
            f"🎬 ចំណងជើង: *{result.title[:60]}*\n"
            f"📦 ទំហំ: *{result.file_size_mb} MB*\n\n"
            f"💡 _អ្នកអាចចុចទាញយកជា MP3 ឬរូប Cover ខាងក្រោម_ 👇",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
    except Exception:
        pass
        
    await chat.send_action("upload_video")
    
    # Send the video file
    try:
        caption = (
            f"🎬 *{result.title}*\n"
            f"👤 អ្នកបង្កើត: {result.uploader}\n"
            f"📦 ទំហំ: {result.file_size_mb} MB\n\n"
            f"✨ ទាញយកដោយ Smart Assistant Bot 🚀"
        )
        
        with open(result.file_path, "rb") as video_file:
            await update.message.reply_video(
                video=video_file,
                caption=caption,
                duration=result.duration,
                supports_streaming=True,
                reply_markup=reply_markup,
                parse_mode="Markdown",
                read_timeout=900.0,
                write_timeout=900.0,
            )
            
        log_download(chat.id, url, result.title)
        
        try:
            await status_msg.delete()
        except Exception:
            pass
            
    except Exception as e:
        logger.error(f"Failed to send video: {e}")
        await update.message.reply_text(
            f"❌ *កំហុសក្នុងការផ្ញើវីដេអូ៖* {str(e)[:150]}\n\n"
            f"👉 អ្នកអាចចុចប៊ូតុងខាងលើដើម្បីទាញយកផ្ទាល់បាន!",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
    finally:
        cleanup_file(result.file_path)

async def handle_media_download_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Handle callbacks for MP3 extraction or HD Cover download."""
    query = update.callback_query
    data = query.data
    
    if not (data.startswith("dlmp3_") or data.startswith("dlthumb_") or data.startswith("dlqual_")):
        return False
        
    chat = query.message.chat
    
    if data.startswith("dlmp3_"):
        token = data.replace("dlmp3_", "")
        url = URL_TOKEN_CACHE.get(token)
        if not url:
            await query.answer("❌ Link បានផុតកំណត់ហើយ សូមផ្ញើ Link ម្តងទៀត។", show_alert=True)
            return True
            
        await query.answer("⏳ កំពុងបម្លែង និងទាញយកសំឡេង MP3...")
        await chat.send_action("upload_voice")
        res = await download_audio_async(url)
        if not res.success or not res.file_path:
            await chat.send_message(f"❌ មិនអាចទាញយកសំឡេងបានទេ៖ {res.error_message}")
            return True
            
        try:
            with open(res.file_path, "rb") as audio_file:
                await chat.send_audio(
                    audio=audio_file,
                    title=res.title,
                    performer=res.uploader,
                    duration=res.duration,
                    caption=f"🎵 *{res.title}*\n📦 ទំហំ៖ {res.file_size_mb} MB\n✨ Smart Assistant Bot",
                    parse_mode="Markdown",
                    read_timeout=600.0,
                )
        except Exception as e:
            logger.error(f"Error sending audio: {e}")
            await chat.send_message(f"❌ កំហុសក្នុងការផ្ញើសំឡេង៖ {str(e)[:100]}")
        finally:
            cleanup_file(res.file_path)
        return True
        
    elif data.startswith("dlthumb_"):
        token = data.replace("dlthumb_", "")
        url = URL_TOKEN_CACHE.get(token)
        if not url:
            await query.answer("❌ Link បានផុតកំណត់ហើយ សូមផ្ញើ Link ម្តងទៀត។", show_alert=True)
            return True
            
        await query.answer("⏳ កំពុងទាញយករូប Thumbnail HD...")
        await chat.send_action("upload_photo")
        thumb_path = await download_thumbnail_hd(url)
        if not thumb_path:
            await chat.send_message("❌ មិនអាចទាញយករូបភាព Cover បានទេ។")
            return True
            
        try:
            with open(thumb_path, "rb") as photo_file:
                await chat.send_photo(
                    photo=photo_file,
                    caption="🖼️ *រូបភាព Thumbnail / Cover (High Definition)* ✨",
                    parse_mode="Markdown",
                )
        except Exception as e:
            logger.error(f"Error sending thumbnail: {e}")
            await chat.send_message(f"❌ កំហុសក្នុងការផ្ញើរូបភាព៖ {str(e)[:100]}")
        finally:
            cleanup_file(thumb_path)
        return True
        
    return False
