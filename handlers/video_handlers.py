import os
import asyncio
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from services.video_downloader import extract_video_url, download_video_async, cleanup_file
from database import log_download
from handlers.command_handlers import get_main_menu_keyboard

logger = logging.getLogger(__name__)

async def handle_video_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Detect and process video download requests."""
    text = update.message.text
    if not text:
        return
        
    chat = update.effective_chat

    # Quick routing for persistent bottom keyboard buttons
    if text == "🏠 ផ្ទាំង Menu មេ":
        from handlers.command_handlers import start_command
        await start_command(update, context)
        return
    elif text == "🗓️ ប្រតិទិនបុណ្យជាតិ":
        from handlers.command_handlers import calendar_command
        await calendar_command(update, context)
        return
    elif text == "⏳ ថ្ងៃបុណ្យបន្ទាប់":
        from handlers.command_handlers import upcoming_command
        await upcoming_command(update, context)
        return
    elif text == "📥 របៀបទាញយក":
        help_msg = (
            "📥 *របៀបទាញយកវីដេអូ៖*\n\n"
            "1. ចូលទៅកាន់ TikTok, YouTube, Facebook, Instagram ឬ X/Twitter\n"
            "2. ចុចពាក្យ **Share** រួចជ្រើសរើស **Copy Link**\n"
            "3. ផ្ញើ (Paste) Link ចូលក្នុង Bot នេះភ្លាមៗ\n"
            "4. Bot នឹងទាញយកវីដេអូ និងផ្ញើជូនលោកអ្នកដោយស្វ័យប្រវត្ត!"
        )
        await update.message.reply_text(help_msg, parse_mode="Markdown")
        return

    url = extract_video_url(text)
    
    # If not a URL, suggest menu options
    if not url:
        reply_msg = (
            "🤖 ខ្ញុំពុំទាន់ឃើញមាន Link វីដេអូនៅឡើយទេ។\n\n"
            "👉 សូមផ្ញើ Link ពី **TikTok, YouTube, Facebook, Instagram ឬ X** ដើម្បីឱ្យខ្ញុំទាញយកវីដេអូជូន\n"
            "ឬចុចមើលប្រតិទិនថ្ងៃឈប់សម្រាកបុណ្យជាតិខាងក្រោម៖"
        )
        await update.message.reply_text(
            reply_msg,
            reply_markup=get_main_menu_keyboard(chat.id),
            parse_mode="Markdown"
        )
        return
        
    # Send processing status
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
        
    # Build fast direct link button if available
    action_buttons = []
    if result.direct_web_url:
        action_buttons.append([InlineKeyboardButton("⚡ មើល / Download ផ្ទាល់ (No Wait)", url=result.direct_web_url)])
    reply_markup = InlineKeyboardMarkup(action_buttons) if action_buttons else None

    # Send uploading status
    try:
        await status_msg.edit_text(
            f"📤 *ទាញយកជោគជ័យ!* កំពុង Upload វីដេអូទៅ Telegram...\n"
            f"🎬 ចំណងជើង: *{result.title[:60]}*\n"
            f"📦 ទំហំ: *{result.file_size_mb} MB*\n\n"
            f"💡 _អ្នកអាចចុចប៊ូតុងខាងក្រោមដើម្បីមើល ឬទាញយកភ្លាមៗ_ 👇",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
    except Exception:
        pass
        
    await chat.send_action("upload_video")
    
    # Send the video file with extended upload timeout (15 mins) and retry
    try:
        uploaded = False
        for attempt in range(2):
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
                    
                # Log download to database
                log_download(chat.id, url, result.title)
                uploaded = True
                
                # Delete temporary status message
                try:
                    await status_msg.delete()
                except Exception:
                    pass
                break
                
            except Exception as e:
                logger.warning(f"Upload attempt {attempt + 1} failed: {e}")
                if attempt == 0:
                    await asyncio.sleep(2)
                else:
                    logger.error(f"Failed to send video after retries: {e}")
                    await update.message.reply_text(
                        f"❌ *កំហុសក្នុងការផ្ញើវីដេអូ៖* {str(e)[:150]}\n\n"
                        f"👉 អ្នកអាចចុចប៊ូតុងខាងលើដើម្បីទាញយកផ្ទាល់បាន!",
                        reply_markup=reply_markup,
                        parse_mode="Markdown"
                    )
    finally:
        # Always clean up temporary file
        cleanup_file(result.file_path)
