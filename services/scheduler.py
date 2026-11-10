import asyncio
import logging
from datetime import time, datetime, timedelta
from typing import Optional
from telegram import InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application
import pytz

from config import (
    BOT_TIMEZONE,
    ALERT_HOUR,
    ALERT_MINUTE,
    WEATHER_ALERT_HOUR,
    WEATHER_ALERT_MINUTE,
    AUTO_CLEAN_MORNING_HOUR,
    AUTO_CLEAN_MORNING_MINUTE,
    AUTO_CLEAN_NOON_HOUR,
    AUTO_CLEAN_NOON_MINUTE,
)
from database import (
    get_active_subscribers,
    get_active_weather_subscribers,
    get_due_reminders,
    mark_reminder_done,
    get_expired_auto_clean_messages,
    delete_auto_clean_message_records,
    get_all_auto_clean_chats,
    get_auto_clean_messages_for_chat,
    clear_auto_clean_messages_for_chat,
    record_auto_clean_message,
)
from services.holiday_calendar import get_today_holiday, format_alert_message
from services.weather_service import fetch_weather, format_weather_message
from services.news_service import generate_morning_news_digest

logger = logging.getLogger(__name__)

async def send_holiday_alert_to_subscribers(app: Application, custom_message: Optional[str] = None):
    """Broadcast holiday alert to all active subscribers at 4:00 AM."""
    holiday = get_today_holiday()
    if not holiday and not custom_message:
        logger.info("Today is not a public holiday. No alert sent.")
        return 0
    
    if custom_message:
        message_text = custom_message
    else:
        message_text = format_alert_message(holiday)
        
    subscribers = get_active_subscribers()
    if not subscribers:
        logger.info("No subscribers found for holiday alert.")
        return 0
        
    sent_count = 0
    for chat_id in subscribers:
        try:
            await app.bot.send_message(
                chat_id=chat_id,
                text=message_text,
                parse_mode="Markdown"
            )
            sent_count += 1
            await asyncio.sleep(0.05)  # Rate limit protection
        except Exception as e:
            logger.warning(f"Failed to send holiday alert to chat_id {chat_id}: {e}")
            
    logger.info(f"Holiday alert sent to {sent_count}/{len(subscribers)} subscribers.")
    return sent_count

async def send_daily_weather_to_subscribers(app: Application):
    """Broadcast daily 5:00 AM weather report based on each user's location."""
    subscribers = get_active_weather_subscribers()
    if not subscribers:
        logger.info("No subscribers found for daily weather alert.")
        return 0
        
    sent_count = 0
    weather_cache = {}
    
    for sub in subscribers:
        chat_id = sub["chat_id"]
        lat = sub.get("latitude", 11.5564)
        lon = sub.get("longitude", 104.9282)
        loc_name = sub.get("location_name", "រាជធានីភ្នំពេញ")
        
        cache_key = f"{round(lat, 3)}_{round(lon, 3)}"
        if cache_key in weather_cache:
            w_data = weather_cache[cache_key]
        else:
            w_data = await fetch_weather(lat, lon)
            if w_data:
                weather_cache[cache_key] = w_data
                
        if not w_data:
            logger.warning(f"Failed to fetch weather for {loc_name} ({lat}, {lon})")
            continue
            
        message_text = format_weather_message(w_data, loc_name, is_daily_alert=True)
        try:
            await app.bot.send_message(
                chat_id=chat_id,
                text=message_text,
                parse_mode="Markdown"
            )
            sent_count += 1
            await asyncio.sleep(0.05)
        except Exception as e:
            logger.warning(f"Failed to send 5AM weather alert to chat_id {chat_id}: {e}")
            
    logger.info(f"5:00 AM Weather alert sent to {sent_count}/{len(subscribers)} subscribers.")
    return sent_count

async def daily_holiday_job(context):
    """JobQueue callback function executed daily at 4:00 AM."""
    logger.info("Executing scheduled 4:00 AM Cambodia holiday check...")
    await send_holiday_alert_to_subscribers(context.application)

async def daily_weather_job(context):
    """JobQueue callback function executed daily at 5:00 AM."""
    logger.info("Executing scheduled 5:00 AM Cambodia daily weather alert...")
    await send_daily_weather_to_subscribers(context.application)

async def daily_news_job(context):
    """JobQueue callback function executed daily at 7:00 AM to send VIP Morning Executive Briefing."""
    logger.info("Executing scheduled 7:00 AM Cambodia VIP Morning Executive Briefing...")
    subscribers = get_active_subscribers()
    if not subscribers:
        logger.info("No subscribers found for morning briefing.")
        return
        
    from services.briefing_service import generate_executive_briefing
    from handlers.command_handlers import get_briefing_keyboard

    sent_count = 0
    for chat_id in subscribers:
        try:
            briefing_text = await generate_executive_briefing(chat_id)
            await context.application.bot.send_message(
                chat_id=chat_id,
                text=briefing_text,
                reply_markup=get_briefing_keyboard(),
                parse_mode="Markdown",
                disable_web_page_preview=True
            )
            sent_count += 1
            await asyncio.sleep(0.05)
        except Exception as e:
            logger.warning(f"Failed to send VIP morning briefing to {chat_id}: {e}")
    logger.info(f"7:00 AM Morning Executive Briefing sent to {sent_count}/{len(subscribers)} subscribers.")

async def check_reminders_job(context):
    """JobQueue callback executed every 60 seconds to fire due reminders."""
    now_iso = datetime.utcnow().isoformat()
    due_reminders = get_due_reminders(now_iso)
    for rem in due_reminders:
        try:
            msg = (
                f"⏰ *[សារដាស់តឿនរបស់អ្នក (Reminder)]* 🔔\n\n"
                f"🕒 *ម៉ោង៖* `{rem['time_str']}`\n"
                f"📝 *កិច្ចការ៖* {rem['message']}\n\n"
                f"✨ កុំភ្លេចរៀបចំឱ្យបានរួចរាល់ណា៎! 🙌"
            )
            await context.application.bot.send_message(
                chat_id=rem["chat_id"],
                text=msg,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🗑️ លុបសារដាស់តឿននេះ", callback_data="btn_delete_this_msg")]
                ]),
                parse_mode="Markdown"
            )
            mark_reminder_done(rem["id"])
            logger.info(f"Triggered reminder {rem['id']} for chat_id {rem['chat_id']}")
        except Exception as e:
            logger.warning(f"Failed to deliver reminder {rem['id']}: {e}")

async def scheduled_clear_history_job(context):
    """
    Scheduled job executed twice daily at 3:00 AM and 12:00 PM (Asia/Phnom_Penh).
    Clears all chat history for all registered chats that have auto-clean enabled.
    """
    logger.info("Executing scheduled twice-daily chat history clean (3:00 AM / 12:00 PM)...")
    try:
        active_chats = get_all_auto_clean_chats()
        if not active_chats:
            logger.info("No active auto-clean chats found.")
            return

        from handlers.command_handlers import get_main_menu_keyboard

        cleaned_chats = 0
        for chat_id in active_chats:
            try:
                from services.chat_cleaner_service import purge_chat_history
                records = get_auto_clean_messages_for_chat(chat_id)
                tracked_mids = [r[1] for r in records]
                highest_id = max(tracked_mids) if tracked_mids else None

                # Purge all messages across chat history (both old and new)
                await purge_chat_history(
                    bot=context.application.bot,
                    chat_id=chat_id,
                    current_msg_id=highest_id,
                    sweep_depth=600,
                    extra_ids=tracked_mids
                )

                # Clear application user_data tracking for this chat if available
                if hasattr(context.application, "user_data") and chat_id in context.application.user_data:
                    context.application.user_data[chat_id].pop("last_bot_msg_id", None)
                    context.application.user_data[chat_id].pop("last_menu_id", None)
                    context.application.user_data[chat_id].pop("last_remind_msg_id", None)

                # 6. Send a fresh main menu so user is greeted with a clean screen
                notice_text = (
                    "🧹 *ការសម្អាតប្រវត្តិសារស្វ័យប្រវត្តិ (Auto-Clean History)* ✨\n\n"
                    "ប្រព័ន្ធបានសម្អាតប្រវត្តិសារទាំងអស់ដោយស្វ័យប្រវត្ត (តាមកាលវិភាគម៉ោង ៣:០០ ព្រឹក និង ១២:០០ ថ្ងៃត្រង់)។\n"
                    "ការជជែករបស់អ្នកឥឡូវនេះមានសភាពស្អាតស្រឡះជានិច្ច! 🌿\n\n"
                    "សូមជ្រើសរើសមុខងារដែលចង់ប្រើប្រាស់បន្តខាងក្រោម៖"
                )
                sent_menu = await context.application.bot.send_message(
                    chat_id=chat_id,
                    text=notice_text,
                    reply_markup=get_main_menu_keyboard(chat_id),
                    parse_mode="Markdown"
                )
                record_auto_clean_message(chat_id, sent_menu.message_id)
                if hasattr(context.application, "user_data") and chat_id in context.application.user_data:
                    context.application.user_data[chat_id]["last_bot_msg_id"] = sent_menu.message_id
                    context.application.user_data[chat_id]["last_menu_id"] = sent_menu.message_id

                cleaned_chats += 1
                await asyncio.sleep(0.05)  # Rate limit protection
            except Exception as e:
                logger.warning(f"Failed to clear history for chat {chat_id}: {e}")

        logger.info(f"Twice-daily chat history clean completed for {cleaned_chats}/{len(active_chats)} chats.")
    except Exception as e:
        logger.error(f"Error in scheduled_clear_history_job: {e}")

async def check_auto_clean_job(context):
    """
    Check and auto-delete messages that are older than 20 minutes (retained for compatibility).
    """
    try:
        now_utc = datetime.utcnow()
        cutoff_iso = (now_utc - timedelta(minutes=20)).isoformat()
        expired = get_expired_auto_clean_messages(cutoff_iso)
        if not expired:
            return

        record_ids_to_delete = []
        for rec_id, chat_id, msg_id in expired:
            record_ids_to_delete.append(rec_id)
            try:
                await context.application.bot.delete_message(chat_id=chat_id, message_id=msg_id)
            except Exception:
                pass

        delete_auto_clean_message_records(record_ids_to_delete)
        logger.debug(f"Auto-cleaned {len(record_ids_to_delete)} messages older than 20 minutes.")
    except Exception as e:
        logger.warning(f"Error in check_auto_clean_job: {e}")

async def check_crypto_alerts_job(context):
    """Check active crypto price alert thresholds and trigger notifications."""
    try:
        from services.crypto_service import check_and_trigger_crypto_alerts
        triggered = await check_and_trigger_crypto_alerts(context.application.bot)
        if triggered > 0:
            logger.info(f"Triggered and delivered {triggered} crypto price alerts.")
    except Exception as e:
        logger.debug(f"Error in check_crypto_alerts_job: {e}")

def setup_scheduler(app: Application):
    """Set up the daily 4:00 AM holiday, 5:00 AM weather alerts, 7:00 AM news, reminders, and twice-daily 3AM/12PM auto-clean."""
    job_queue = app.job_queue
    if not job_queue:
        logger.warning("JobQueue is not enabled in Application.")
        return
        
    # 1. Holiday Alert: 4:00 AM (Asia/Phnom_Penh)
    holiday_alert_time = time(hour=ALERT_HOUR, minute=ALERT_MINUTE, tzinfo=BOT_TIMEZONE)
    job_queue.run_daily(
        daily_holiday_job,
        time=holiday_alert_time,
        name="daily_cambodia_holiday_alert"
    )
    logger.info(f"Registered daily 4:00 AM holiday alert at {holiday_alert_time} ({BOT_TIMEZONE}).")

    # 2. Daily Weather Alert: 5:00 AM (Asia/Phnom_Penh)
    weather_alert_time = time(hour=WEATHER_ALERT_HOUR, minute=WEATHER_ALERT_MINUTE, tzinfo=BOT_TIMEZONE)
    job_queue.run_daily(
        daily_weather_job,
        time=weather_alert_time,
        name="daily_cambodia_weather_alert"
    )
    logger.info(f"Registered daily 5:00 AM weather alert at {weather_alert_time} ({BOT_TIMEZONE}).")

    # 3. Daily Morning News Digest: 7:00 AM (Asia/Phnom_Penh)
    news_alert_time = time(hour=7, minute=0, tzinfo=BOT_TIMEZONE)
    job_queue.run_daily(
        daily_news_job,
        time=news_alert_time,
        name="daily_cambodia_morning_news"
    )
    logger.info(f"Registered daily 7:00 AM morning news digest at {news_alert_time} ({BOT_TIMEZONE}).")

    # 4. Custom Reminders: Check every 60 seconds
    job_queue.run_repeating(
        check_reminders_job,
        interval=60,
        first=10,
        name="custom_reminders_checker"
    )
    logger.info("Registered custom reminders checker job (every 60s).")

    # 5. Scheduled Twice-Daily Auto-Clean: 3:00 AM & 12:00 PM (Asia/Phnom_Penh)
    clean_3am_time = time(hour=AUTO_CLEAN_MORNING_HOUR, minute=AUTO_CLEAN_MORNING_MINUTE, tzinfo=BOT_TIMEZONE)
    clean_12pm_time = time(hour=AUTO_CLEAN_NOON_HOUR, minute=AUTO_CLEAN_NOON_MINUTE, tzinfo=BOT_TIMEZONE)
    job_queue.run_daily(
        scheduled_clear_history_job,
        time=clean_3am_time,
        name="daily_3am_history_clean"
    )
    job_queue.run_daily(
        scheduled_clear_history_job,
        time=clean_12pm_time,
        name="daily_12pm_history_clean"
    )
    logger.info(f"Registered twice-daily chat auto-clean at 3:00 AM and 12:00 PM ({BOT_TIMEZONE}).")

    # 6. Crypto Price Alert Checker: Check every 5 minutes (300s)
    job_queue.run_repeating(
        check_crypto_alerts_job,
        interval=300,
        first=45,
        name="crypto_price_alerts_checker"
    )
    logger.info("Registered crypto price alerts checker job (every 300s).")
