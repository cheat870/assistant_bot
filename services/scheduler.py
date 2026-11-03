import asyncio
import logging
from datetime import time
from typing import Optional
from telegram.ext import Application
import pytz

from config import (
    BOT_TIMEZONE,
    ALERT_HOUR,
    ALERT_MINUTE,
    WEATHER_ALERT_HOUR,
    WEATHER_ALERT_MINUTE,
)
from database import get_active_subscribers, get_active_weather_subscribers
from services.holiday_calendar import get_today_holiday, format_alert_message
from services.weather_service import fetch_weather, format_weather_message

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
    # Cache weather data for identical lat/lon to save requests
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
            await asyncio.sleep(0.05)  # Telegram API rate limit protection
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

def setup_scheduler(app: Application):
    """Set up the daily 4:00 AM holiday and 5:00 AM weather alerts using telegram JobQueue."""
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
