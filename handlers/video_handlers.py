import os
import uuid
import asyncio
import logging
from typing import Dict, Optional
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from services.video_downloader import (
    extract_video_url,
    download_video_async,
    download_audio_async,
    download_thumbnail_hd,
    cleanup_file,
)
from database import (
    log_download,
    is_ai_mode,
    is_antispam_enabled,
    save_media_token,
    get_media_token_url,
)
from services.ai_service import query_continuous_ai
from services.moderation_service import check_spam
from services.expense_service import (
    parse_expense_text,
    record_transaction,
    format_record_success,
)
from handlers.command_handlers import (
    get_main_menu_keyboard,
    start_command,
    weather_command,
    calendar_command,
    finance_command,
    reminders_command,
    aimode_command,
    budget_command,
    news_command,
    briefing_command,
    compress_command,
    safe_reply_text,
)

logger = logging.getLogger(__name__)

# Temporary in-memory cache for media tokens (token -> URL)
URL_TOKEN_CACHE: Dict[str, str] = {}

def get_or_create_media_token(url: str) -> str:
    """Map URL to a short token for callback data (max 64 bytes in Telegram)."""
    # Keep cache from growing unboundedly
    if len(URL_TOKEN_CACHE) > 500:
        keys = list(URL_TOKEN_CACHE.keys())[:100]
        for k in keys:
            URL_TOKEN_CACHE.pop(k, None)
            
    for token, cached_url in URL_TOKEN_CACHE.items():
        if cached_url == url:
            return token
            
    token = uuid.uuid4().hex[:10]
    URL_TOKEN_CACHE[token] = url
    try:
        save_media_token(token, url)
    except Exception as e_tok:
        logger.warning(f"Could not persist media token: {e_tok}")
    return token

def resolve_media_url(token: str, query=None) -> Optional[str]:
    """Retrieve original media URL from memory cache, SQLite, or message context."""
    # 1. Check in-memory cache
    if token and token in URL_TOKEN_CACHE:
        return URL_TOKEN_CACHE[token]

    # 2. Check SQLite persistent table
    if token:
        try:
            db_url = get_media_token_url(token)
            if db_url:
                URL_TOKEN_CACHE[token] = db_url
                return db_url
        except Exception:
            pass

    # 3. Fallback to message context if available
    if query and query.message:
        msg = query.message
        # Check original user request text if this message is a reply
        if msg.reply_to_message:
            candidate_text = msg.reply_to_message.text or msg.reply_to_message.caption or ""
            extracted = extract_video_url(candidate_text)
            if extracted:
                if token:
                    URL_TOKEN_CACHE[token] = extracted
                    try:
                        save_media_token(token, extracted)
                    except Exception:
                        pass
                return extracted

        # Check caption of current message
        if msg.caption:
            extracted = extract_video_url(msg.caption)
            if extracted:
                return extracted

        # Check inline keyboard buttons (e.g. direct download URL)
        if msg.reply_markup and msg.reply_markup.inline_keyboard:
            for row in msg.reply_markup.inline_keyboard:
                for btn in row:
                    if btn.url and any(domain in btn.url for domain in ["tiktok.com", "youtube.com", "youtu.be", "facebook.com", "fb.watch", "instagram.com"]):
                        return btn.url

    return None

async def handle_video_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Detect and process video download requests or AI Continuous Chat."""
    text = update.message.text
    if not text:
        return
        
    chat = update.effective_chat

    # 1. Anti-Spam protection for Group & Supergroup
    if chat.type in ["group", "supergroup"] and is_antispam_enabled(chat.id):
        is_spam, reason = check_spam(text)
        if is_spam:
            try:
                await update.message.delete()
                warn_msg = await context.bot.send_message(
                    chat_id=chat.id,
                    text=f"🛡️ *[Auto-Mod]* បានលុបសារផ្សាយពាណិជ្ជកម្ម/Spam ដោយស្វ័យប្រវត្តិ ({reason})។",
                    parse_mode="Markdown"
                )
                await asyncio.sleep(5)
                await warn_msg.delete()
            except Exception as e:
                logger.warning(f"Failed to auto-delete spam: {e}")
            return

    # 2. Record message for 20-minute auto-delete watcher
    if chat.type == "private" and update.message:
        try:
            from database import record_auto_clean_message
            record_auto_clean_message(chat.id, update.message.message_id)
        except Exception:
            pass

    # Quick routing for persistent bottom keyboard buttons & friendly text triggers
    clean_text = text.strip()
    norm_text = clean_text.replace("\ufe0f", "").replace("\ufe0e", "").replace("\u200b", "").strip()
    norm_lower = norm_text.lower()

    if any(k in norm_text for k in ["ផ្ទាំង Menu", "Menu", "មឺនុយ", "ផ្ទាំងដើម"]) or norm_lower in ["menu", "/menu", "start", "/start"]:
        await start_command(update, context)
        return
    elif any(k in norm_text for k in ["ចំណូល-ចំណាយ", "ចំណាយ", "ចំណូល"]) or norm_lower in ["budget", "/budget"]:
        # If it's a specific transaction (has numbers/currencies), let step 3 parse it
        parsed_exp = parse_expense_text(text)
        if parsed_exp:
            record_transaction(chat.id, parsed_exp)
            msg = format_record_success(parsed_exp)
            from handlers.command_handlers import send_clean_response
            exp_kb = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("📊 មើល Budget", callback_data="btn_budget"),
                    InlineKeyboardButton("🔙 Menu ដើម", callback_data="btn_back_main")
                ]
            ])
            await send_clean_response(update, context, msg, reply_markup=exp_kb)
            return
        await budget_command(update, context)
        return
    elif any(k in norm_text for k in ["សង្ខេប", "briefing", "vip"]) or norm_lower in ["briefing", "/briefing"]:
        await briefing_command(update, context)
        return
    elif any(k in norm_text for k in ["បង្រួម", "បម្លែង", "compress", "convert"]) or norm_lower in ["compress", "/compress", "convert", "/convert"]:
        await compress_command(update, context)
        return
    elif "ព័ត៌មាន" in norm_text or norm_lower in ["news", "/news"]:
        await news_command(update, context)
        return
    elif "អាកាសធាតុ" in norm_text or norm_lower in ["weather", "/weather"]:
        await weather_command(update, context)
        return
    elif any(k in norm_text for k in ["ប្រតិទិន", "បុណ្យជាតិ"]) or norm_lower in ["calendar", "/calendar", "holidays", "/holidays"]:
        await calendar_command(update, context)
        return
    elif any(k in norm_text for k in ["សេដ្ឋកិច្ច", "មាស", "សាំង", "អត្រាប្តូរប្រាក់"]) or norm_lower in ["finance", "/finance", "rate", "/rate"]:
        await finance_command(update, context)
        return
    elif any(k in norm_text for k in ["Crypto", "crypto", "TON", "ton", "Bitcoin", "bitcoin", "BTC", "btc", "តម្លៃកាក់"]) or norm_lower in ["crypto", "/crypto", "ton", "/ton", "btc", "/btc", "coin", "/coin"]:
        from handlers.command_handlers import crypto_command
        await crypto_command(update, context)
        return
    elif any(k in norm_text for k in ["សរសេរ caption", "caption", "Content", "content", "ផុសលក់", "tiktok script"]) or norm_lower in ["caption", "/caption", "content", "/content", "post", "/post", "script", "/script"]:
        from handlers.command_handlers import content_command
        await content_command(update, context)
        return
    elif any(k in norm_text for k in ["រំលឹក"]) or any(k in norm_lower for k in ["reminders", "reminder"]):
        await reminders_command(update, context)
        return
    elif any(k in norm_text for k in ["សម្អាត", "clean", "clear"]) or norm_lower in ["clean", "/clean", "clear", "/clear"]:
        from handlers.command_handlers import clean_chat_command
        await clean_chat_command(update, context)
        return
    elif any(k in norm_text for k in ["AI Chat", "ai chat"]) or norm_lower in ["ai", "aimode", "/aimode"]:
        await aimode_command(update, context)
        return
    elif any(k in norm_text for k in ["របៀបទាញយក", "របៀបប្រើ", "ជំនួយ"]) or norm_lower in ["help", "/help"]:
        await help_command(update, context)
        return

    # 3. Check for natural language expense & income tracking (e.g. ចាយ 20,000៛ ញ៉ាំបាយ, ចំណាយ 5$ coffee)
    parsed_expense = parse_expense_text(text)
    if parsed_expense:
        record_transaction(chat.id, parsed_expense)
        msg = format_record_success(parsed_expense)
        from handlers.command_handlers import send_clean_response
        exp_kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("📊 មើល Budget", callback_data="btn_budget"),
                InlineKeyboardButton("🔙 Menu ដើម", callback_data="btn_back_main")
            ]
        ])
        await send_clean_response(update, context, msg, reply_markup=exp_kb)
        return

    # 4. Check if this is a follow-up question replying to a PDF summary
    reply_msg = update.message.reply_to_message
    if reply_msg and reply_msg.from_user and reply_msg.from_user.is_bot:
        from database import get_pdf_session
        from services.pdf_service import answer_pdf_question
        pdf_session = get_pdf_session(chat.id)
        reply_text_raw = reply_msg.text or reply_msg.caption or ""
        if pdf_session and any(k in reply_text_raw for k in ["📄", "PDF", "ឈ្មោះឯកសារ", "ទំព័រ", "សេចក្តីសង្ខេប"]):
            await chat.send_action("typing")
            ans = await answer_pdf_question(
                document_context=pdf_session.get("extracted_text") or pdf_session.get("summary", ""),
                question=text,
                filename=pdf_session.get("filename", "document.pdf")
            )
            from handlers.command_handlers import safe_reply_text
            await safe_reply_text(update.message, ans)
            return

    url = extract_video_url(text)
    
    # If not a URL, check if continuous AI mode is active or auto-extract memory
    if not url:
        # Check for automatic Long-Term Memory mining (music taste, habits, birthday)
        from services.memory_service import auto_extract_and_save_facts
        memory_fact = auto_extract_and_save_facts(chat.id, text)

        if is_ai_mode(chat.id):
            await chat.send_action("typing")
            ai_reply = await query_continuous_ai(chat.id, text)
            exit_button = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔕 បិទ AI Mode", callback_data="btn_toggle_aimode")]
            ])
            from handlers.command_handlers import safe_reply_text
            await safe_reply_text(update.message, ai_reply, reply_markup=exit_button)
            return

        if memory_fact:
            confirm_text = (
                f"{memory_fact}\n\n"
                f"🧠 *Bot បានកត់ត្រាចូល Long-Term Memory រួចរាល់ហើយ!* ✨\n"
                f"ខ្ញុំនឹងចងចាំចំណុចនេះ ដើម្បីផ្តល់អនុសាសន៍ និងចម្លើយដែលត្រូវចិត្តអ្នកជានិច្ច។"
            )
            from handlers.command_handlers import send_clean_response, get_back_keyboard
            await send_clean_response(update, context, confirm_text, reply_markup=get_back_keyboard())
            return
            
        reply_msg = (
            "🤖 ខ្ញុំពុំទាន់ឃើញមាន Link វីដេអូនៅឡើយទេ។\n\n"
            "👉 សូមផ្ញើ Link ពី **TikTok, YouTube, Facebook, Instagram ឬ X** ដើម្បីឱ្យខ្ញុំទាញយកវីដេអូជូន\n"
            "ឬចុច Menu ខាងក្រោមដើម្បីប្រើមុខងារផ្សេងៗ៖"
        )
        from handlers.command_handlers import send_clean_response
        await send_clean_response(
            update=update,
            context=context,
            text=reply_msg,
            reply_markup=get_main_menu_keyboard(chat.id)
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

    # Handle TikTok Photo Slideshow / Live Photos mode
    if result.is_photo_slideshow and result.images:
        try:
            await status_msg.edit_text(
                f"📸 *បានរកឃើញ Photo Slideshow / Live Photos!* កំពុង Upload រូបភាព HD ទាំង *{len(result.images)} សន្លឹក* ទៅ Telegram...\n"
                f"🖼️ ចំណងជើង: *{result.title[:60]}*\n"
                f"👤 អ្នកបង្កើត: *{result.uploader}*\n\n"
                f"សូមរង់ចាំបន្តិចណា៎! 🚀",
                parse_mode="Markdown"
            )
        except Exception:
            pass

        await chat.send_action("upload_photo")
        from telegram import InputMediaPhoto

        photo_caption = (
            f"📸 *{result.title}*\n"
            f"🖼️ ចំនួនរូបថត: *{len(result.images)} សន្លឹក (HD)*\n"
            f"👤 អ្នកបង្កើត: {result.uploader}\n\n"
            f"✨ ទាញយកដោយ Smart Assistant Bot 🚀"
        )

        all_sent_photo_ids = []
        try:
            chunks = [result.images[i:i + 10] for i in range(0, len(result.images), 10)]
            for c_idx, chunk in enumerate(chunks):
                media = []
                for i, img_path in enumerate(chunk):
                    with open(img_path, "rb") as f_img:
                        img_bytes = f_img.read()
                    cap = photo_caption if c_idx == 0 and i == 0 else None
                    media.append(InputMediaPhoto(media=img_bytes, caption=cap, parse_mode="Markdown"))

                sent_group = await update.message.reply_media_group(media=media)
                for sm in sent_group:
                    if sm.photo:
                        all_sent_photo_ids.append(sm.photo[-1].file_id)

            log_download(chat.id, url, result.title)

            # Control buttons for music and channel
            photo_buttons = [
                [InlineKeyboardButton("🎵 ទាញយកបទចម្រៀង (BGM MP3)", callback_data=f"dlmp3_{token}")],
                [InlineKeyboardButton("📻 មើលក្នុង Channel @Song182", url="https://t.me/Song182")]
            ]
            await update.message.reply_text(
                f"✅ *បានផ្ញើរូបថតកម្រិតច្បាស់ HD ទាំងអស់ ({len(result.images)} សន្លឹក) រួចរាល់!* 🖼️\n"
                f"👉 អ្នកអាចចុចប៊ូតុងខាងក្រោមដើម្បីទាញយកបទចម្រៀង BGM នៃរូបភាពនេះបាន 👇",
                reply_markup=InlineKeyboardMarkup(photo_buttons),
                parse_mode="Markdown"
            )

            # Auto-archive photos to @Song182
            if all_sent_photo_ids:
                try:
                    from services.music_archive_service import archive_photos_to_channel
                    asyncio.create_task(
                        archive_photos_to_channel(
                            bot=context.bot,
                            user=update.effective_user,
                            photo_data={
                                "title": result.title,
                                "uploader": result.uploader,
                                "url": url,
                            },
                            sent_photo_file_ids=all_sent_photo_ids
                        )
                    )
                except Exception as e_p_arch:
                    logger.warning(f"Could not auto-archive photos: {e_p_arch}")

            try:
                await status_msg.delete()
            except Exception:
                pass
        except Exception as e_p_send:
            logger.error(f"Failed to send photo slideshow: {e_p_send}")
            await update.message.reply_text(f"❌ *កំហុសក្នុងការផ្ញើរូបភាព៖* {str(e_p_send)[:150]}")
        finally:
            for p in result.images:
                cleanup_file(p)
        return
        
    # Build buttons for MP3, HD Cover, 1080p, 4K, 8K, and direct web link
    buttons = [
        [
            InlineKeyboardButton("💎 1080p FHD", callback_data=f"dlqual_{token}_1080p"),
            InlineKeyboardButton("🔥 4K / Best", callback_data=f"dlqual_{token}_4k"),
            InlineKeyboardButton("🌌 8K Ultra", callback_data=f"dlqual_{token}_8k"),
        ],
        [
            InlineKeyboardButton("🎵 ទាញយកជា MP3", callback_data=f"dlmp3_{token}"),
            InlineKeyboardButton("🖼️ រូប Cover HD", callback_data=f"dlthumb_{token}"),
        ],
        [
            InlineKeyboardButton("📻 មើលក្នុង Channel @Song182", url="https://t.me/Song182")
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
        
        sent_video = None
        with open(result.file_path, "rb") as video_file:
            sent_video = await update.message.reply_video(
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

        # Automatic Channel Archiving to @Song182 (-1003994142170)
        if sent_video and sent_video.video:
            try:
                from services.music_archive_service import archive_video_to_channel
                asyncio.create_task(
                    archive_video_to_channel(
                        bot=context.bot,
                        user=update.effective_user,
                        video_data={
                            "title": result.title,
                            "uploader": result.uploader,
                            "duration": result.duration,
                            "url": url,
                        },
                        sent_video_file_id=sent_video.video.file_id
                    )
                )
            except Exception as e_arch:
                logger.warning(f"Could not auto-archive video to channel: {e_arch}")
        
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
        url = resolve_media_url(token, query)
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
            sent_audio = None
            with open(res.file_path, "rb") as audio_file:
                sent_audio = await chat.send_audio(
                    audio=audio_file,
                    title=res.title,
                    performer=res.uploader,
                    duration=res.duration,
                    caption=f"🎵 *{res.title}*\n📦 ទំហំ៖ {res.file_size_mb} MB\n✨ Smart Assistant Bot",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("📻 ស្តាប់ក្នុង Music Channel", url="https://t.me/Song182")]
                    ]),
                    parse_mode="Markdown",
                    read_timeout=600.0,
                )

            # Auto-archive MP3 to channel @Song182
            if sent_audio and sent_audio.audio:
                try:
                    from services.music_archive_service import archive_song_to_channel
                    dur_sec = res.duration or 0
                    asyncio.create_task(
                        archive_song_to_channel(
                            bot=context.bot,
                            user=update.effective_user,
                            song_data={
                                "title": res.title,
                                "performer": res.uploader,
                                "duration": dur_sec,
                                "duration_str": f"{dur_sec // 60}:{dur_sec % 60:02d}" if dur_sec else "Unknown",
                                "query": url or res.title,
                            },
                            sent_audio_file_id=sent_audio.audio.file_id
                        )
                    )
                except Exception as e_arch_mp3:
                    logger.warning(f"Could not auto-archive MP3 audio: {e_arch_mp3}")
        except Exception as e:
            logger.error(f"Error sending audio: {e}")
            await chat.send_message(f"❌ កំហុសក្នុងការផ្ញើសំឡេង៖ {str(e)[:100]}")
        finally:
            cleanup_file(res.file_path)
        return True
        
    elif data.startswith("dlthumb_"):
        token = data.replace("dlthumb_", "")
        url = resolve_media_url(token, query)
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

    elif data.startswith("dlqual_"):
        parts = data.split("_")
        token = parts[1] if len(parts) > 1 else ""
        qual = parts[2] if len(parts) > 2 else "1080p"
        url = resolve_media_url(token, query)
        if not url:
            await query.answer("❌ Link បានផុតកំណត់ហើយ សូមផ្ញើ Link ម្តងទៀត។", show_alert=True)
            return True

        await query.answer(f"⏳ កំពុងដំណើរការទាញយកកម្រិត {qual.upper()}...")
        status_m = await chat.send_message(
            f"⏳ *កំពុងទាញយកវីដេអូកម្រិតច្បាស់ {qual.upper()} (Ultra HD)...*\n"
            f"សូមរង់ចាំបន្តិចណា៎! 🚀",
            parse_mode="Markdown"
        )
        await chat.send_action("upload_video")

        res = await download_video_async(url, quality=qual)
        if not res.success or not res.file_path:
            err_msg = res.error_message or ""
            is_size_err = any(k in err_msg.lower() for k in ["50", "48", "ធំជាង", "larger than", "max-filesize"])
            if is_size_err:
                web_dl_buttons = []
                import re
                yt_match = re.search(r'(?:v=|\/)([0-9A-Za-z_-]{11})', url)
                if yt_match:
                    vid = yt_match.group(1)
                    web_dl_buttons.append([InlineKeyboardButton("🌐 ទាញយក File 8K/4K ពេញលេញ (SaveFrom)", url=f"https://en.savefrom.net/#url=https://www.youtube.com/watch?v={vid}")])
                    web_dl_buttons.append([InlineKeyboardButton("🚀 ទាញយកតាម Cobalt (No Ads - 8K/4K)", url=f"https://cobalt.tools")])
                elif getattr(res, "direct_web_url", None):
                    web_dl_buttons.append([InlineKeyboardButton("⚡ មើល / Download ផ្ទាល់ (No Wait)", url=res.direct_web_url)])
                web_dl_buttons.append([InlineKeyboardButton("📻 មើលក្នុង Channel @Song182", url="https://t.me/Song182")])

                await status_m.edit_text(
                    f"⚠️ *វីដេអូកម្រិត {qual.upper()} នេះមានទំហំធំ ({res.file_size_mb or '> 50'} MB)!*\n\n"
                    f"Telegram Bot API អនុញ្ញាតឱ្យ Upload វីដេអូត្រឹម **50 MB** ប៉ុណ្ណោះ។\n"
                    f"👉 សូមចុចប៊ូតុងខាងក្រោមដើម្បីទាញយក File {qual.upper()} ដើមពេញលេញដោយផ្ទាល់ ដោយគ្មានដែនកំណត់ទំហំ៖",
                    reply_markup=InlineKeyboardMarkup(web_dl_buttons),
                    parse_mode="Markdown"
                )
                return True

            await status_m.edit_text(
                f"❌ មិនអាចទាញយកកម្រិត {qual.upper()} បានទេ៖ {res.error_message}\n_ប្រភពដើមប្រហែលជាគ្មានកម្រិត {qual.upper()} ឡើយ។_",
                parse_mode="Markdown"
            )
            return True

        # In case the link was a photo slideshow
        if getattr(res, "is_photo_slideshow", False) and getattr(res, "images", None):
            try:
                from telegram import InputMediaPhoto
                media = []
                for idx, img_path in enumerate(res.images[:10]):
                    with open(img_path, "rb") as f_i:
                        media.append(InputMediaPhoto(media=f_i.read(), caption=f"📸 {res.title}" if idx == 0 else None))
                await chat.send_media_group(media=media)
                await status_m.delete()
            except Exception as e_ps:
                logger.error(f"Error sending photo slideshow in dlqual: {e_ps}")
            finally:
                for p in res.images:
                    cleanup_file(p)
            return True

        try:
            caption_tag = "🌌 8K ULTRA HD" if qual == "8k" else f"🎬 *{res.title}* ({qual.upper()})"
            caption = (
                f"🌌 *{res.title}* (8K ULTRA HD)\n"
                f"👤 អ្នកបង្កើត: {res.uploader}\n"
                f"📦 ទំហំ: {res.file_size_mb} MB (កម្រិតច្បាស់បំផុត 8K)\n\n"
                f"✨ ទាញយកដោយ Smart Assistant Bot 🚀"
            ) if qual == "8k" else (
                f"🎬 *{res.title}* ({qual.upper()})\n"
                f"👤 អ្នកបង្កើត: {res.uploader}\n"
                f"📦 ទំហំ: {res.file_size_mb} MB (កម្រិតច្បាស់ខ្ពស់)\n\n"
                f"✨ ទាញយកដោយ Smart Assistant Bot 🚀"
            )
            sent_v = None
            with open(res.file_path, "rb") as video_file:
                sent_v = await chat.send_video(
                    video=video_file,
                    caption=caption,
                    duration=res.duration,
                    supports_streaming=True,
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("📻 មើលក្នុង Channel @Song182", url="https://t.me/Song182")]
                    ]),
                    parse_mode="Markdown",
                    read_timeout=900.0,
                    write_timeout=900.0,
                )

            # Auto-archive HD video to channel @Song182
            if sent_v and sent_v.video:
                try:
                    from services.music_archive_service import archive_video_to_channel
                    asyncio.create_task(
                        archive_video_to_channel(
                            bot=context.bot,
                            user=update.effective_user,
                            video_data={
                                "title": f"{res.title} ({qual.upper()})",
                                "uploader": res.uploader,
                                "duration": res.duration,
                                "url": url,
                            },
                            sent_video_file_id=sent_v.video.file_id
                        )
                    )
                except Exception as e_arch_hd:
                    logger.warning(f"Could not auto-archive HD video to channel: {e_arch_hd}")

            try:
                await status_m.delete()
            except Exception:
                pass
        except Exception as e:
            logger.error(f"Error sending HD video: {e}")
            await chat.send_message(
                f"❌ កំហុសក្នុងការផ្ញើវីដេអូកម្រិត {qual.upper()}៖ {str(e)[:120]}\n\n"
                f"💡 _ប្រសិនបើទំហំ File ធំជាង 50MB (ដែនកំណត់ Telegram) សូមទាញយកកម្រិតធម្មតា ឬមើលតាម Direct Link!_"
            )
        finally:
            cleanup_file(res.file_path)
        return True
        
    return False
