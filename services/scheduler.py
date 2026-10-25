import asyncio
import logging
from datetime import time
from typing import Optional
from telegram.ext import Application
import pytz

from config import BOT_TIMEZONE, ALERT_HOUR, ALERT_MINUTE
from database import get_active_subscribers
from services.holiday_calendar import get_today_holiday, format_alert_message, get_upcoming_holidays

logger = logging.getLogger(__name__)

async def send_holiday_alert_to_subscribers(app: Application, custom_message: Optional[str] = None):
    """Broadcast alert to all active subscribers."""
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
            logger.warning(f"Failed to send alert to chat_id {chat_id}: {e}")
            
    logger.info(f"Holiday alert sent to {sent_count}/{len(subscribers)} subscribers.")
    return sent_count

async def daily_holiday_job(context):
    """JobQueue callback function executed daily at 4:00 AM."""
    logger.info("Executing scheduled 4:00 AM Cambodia holiday check...")
    await send_holiday_alert_to_subscribers(context.application)

def setup_scheduler(app: Application):
    """Set up the daily 4:00 AM Cambodia time alert using telegram JobQueue."""
    job_queue = app.job_queue
    if not job_queue:
        logger.warning("JobQueue is not enabled in Application.")
        return
        
    alert_time = time(hour=ALERT_HOUR, minute=ALERT_MINUTE, tzinfo=BOT_TIMEZONE)
    job_queue.run_daily(
        daily_holiday_job,
        time=alert_time,
        name="daily_cambodia_holiday_alert"
    )
    logger.info(f"Registered daily 4:00 AM holiday alert at {alert_time} ({BOT_TIMEZONE}).")
