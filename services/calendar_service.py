import re
import json
import pytz
import asyncio
import logging
import urllib.parse
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Tuple

from config import BOT_TIMEZONE, GEMINI_API_KEY, TIMEZONE_STR
from database import add_reminder

logger = logging.getLogger(__name__)

CAMBODIA_TZ = BOT_TIMEZONE if hasattr(BOT_TIMEZONE, "localize") else pytz.timezone(TIMEZONE_STR)

def parse_khmer_event_fallback(text: str, base_now: datetime) -> Tuple[datetime, str, str]:
    """Fallback rule-based parser for common Khmer & English appointment strings."""
    kh_digits = {'០':'0', '១':'1', '២':'2', '៣':'3', '៤':'4', '៥':'5', '៦':'6', '៧':'7', '៨':'8', '៩':'9'}
    t = text
    for k, v in kh_digits.items():
        t = t.replace(k, v)

    # Date
    target_date = base_now.date()
    if 'ស្អែក' in t or 'tomorrow' in t.lower():
        target_date += timedelta(days=1)
    elif 'ខានស្អែក' in t:
        target_date += timedelta(days=2)

    # Time extraction: e.g. 'ម៉ោង 2 រសៀល', 'ម៉ោង 14:00', 'ម៉ោង 9 ព្រឹក'
    hour = 14 if 'រសៀល' in t or 'ល្ងាច' in t else 9
    minute = 0
    m = re.search(r'ម៉ោង\s*(\d{1,2})(?::(\d{2}))?\s*(ព្រឹក|រសៀល|ល្ងាច|យប់)?', t)
    if m:
        h = int(m.group(1))
        mi = int(m.group(2)) if m.group(2) else 0
        ampm = m.group(3) or ''
        if ampm in ['រសៀល', 'ល្ងាច', 'យប់'] and h < 12:
            h += 12
        elif ampm == 'ព្រឹក' and h == 12:
            h = 0
        hour = h
        minute = mi
    else:
        # Check standard 14:00 or 2pm
        m2 = re.search(r'(\d{1,2})(?::(\d{2}))?\s*(am|pm|AM|PM)', t)
        if m2:
            h = int(m2.group(1))
            mi = int(m2.group(2)) if m2.group(2) else 0
            ampm = m2.group(3).lower()
            if ampm == 'pm' and h < 12:
                h += 12
            elif ampm == 'am' and h == 12:
                h = 0
            hour = h
            minute = mi

    dt_start_naive = datetime.combine(target_date, datetime.min.time()).replace(hour=hour, minute=minute)
    dt_start = CAMBODIA_TZ.localize(dt_start_naive)

    # Title & Location extraction
    clean = re.sub(r'/(event|schedule)', '', t, flags=re.IGNORECASE)
    clean = re.sub(r'(ស្អែក|ថ្ងៃនេះ|ខានស្អែក|tomorrow|today)', '', clean, flags=re.IGNORECASE)
    clean = re.sub(r'ម៉ោង\s*\d{1,2}(?::\d{2})?\s*(ព្រឹក|រសៀល|ល្ងាច|យប់)?', '', clean)
    clean = re.sub(r'\d{1,2}(?::\d{2})?\s*(am|pm|AM|PM)', '', clean).strip()

    loc = ''
    title = clean
    if 'នៅ' in clean:
        parts = clean.split('នៅ', 1)
        title = parts[0].strip() or 'កម្មវិធីណាត់ជួប'
        loc = parts[1].strip()
    elif 'at' in clean.lower():
        parts = re.split(r'\bat\b', clean, flags=re.IGNORECASE, maxsplit=1)
        title = parts[0].strip() or 'កម្មវិធីណាត់ជួប'
        loc = parts[1].strip()

    title = title or "កម្មវិធីណាត់ជួប"
    return dt_start, title, loc

async def parse_and_create_calendar_event(user_text: str, chat_id: int) -> Tuple[bool, str, Optional[str], Optional[str]]:
    """
    Parse natural language schedule request in Khmer/English using Gemini,
    generate 1-click Google Calendar URL, .ics file string, and schedule a 60-min advance reminder.
    Returns: (success, response_message, google_calendar_url, ics_content)
    """
    now_local = datetime.now(CAMBODIA_TZ)
    current_time_str = now_local.strftime("%Y-%m-%d %H:%M (%A)")

    prompt = (
        "You are an expert natural language schedule and calendar event parser. "
        "The user will give you an appointment, meeting, or event text in Khmer or English. "
        f"Current local time in Cambodia (UTC+7): {current_time_str}.\n\n"
        "User input: " + user_text + "\n\n"
        "Extract these event details:\n"
        "1. title: Title or main action (e.g., 'ណាត់ជួបអតិថិជន')\n"
        "2. location: Location if specified (e.g., 'Brown Bokor') or empty string\n"
        "3. start_time: ISO 8601 string formatted strictly as 'YYYY-MM-DDTHH:MM:SS' in UTC+7 (Cambodia Time)\n"
        "4. end_time: ISO 8601 string formatted strictly as 'YYYY-MM-DDTHH:MM:SS' (defaults to 1 hour after start_time if not specified)\n"
        "5. description: Brief summary in Khmer\n\n"
        "Return STRICT JSON only, no markdown formatting, no backticks, e.g.:\n"
        '{"title": "...", "location": "...", "start_time": "YYYY-MM-DDTHH:MM:SS", "end_time": "YYYY-MM-DDTHH:MM:SS", "description": "..."}'
    )

    try:
        data = None
        try:
            from google import genai
            from google.genai import types
            from services.ai_service import _call_gemini_api

            if GEMINI_API_KEY and GEMINI_API_KEY != "your_gemini_api_key_here":
                client = genai.Client(api_key=GEMINI_API_KEY)
                response = await asyncio.to_thread(
                    _call_gemini_api,
                    client,
                    prompt,
                    "Extract calendar event strictly as JSON."
                )

                res_text = response.text.strip() if response and response.text else ""
                if res_text.startswith("```"):
                    res_text = re.sub(r"^```[a-zA-Z]*\n?", "", res_text)
                    res_text = re.sub(r"\n?```$", "", res_text).strip()

                if res_text:
                    data = json.loads(res_text)
        except Exception as e_ai:
            logger.warning(f"Gemini calendar parsing failed, using rule-based fallback: {e_ai}")

        if data and isinstance(data, dict) and data.get("start_time"):
            title = data.get("title", "កម្មវិធីណាត់ជួប").strip()
            location = data.get("location", "").strip()
            start_str = data.get("start_time", "").strip()
            end_str = data.get("end_time", "").strip()
            description = data.get("description", title).strip()

            dt_start_naive = datetime.fromisoformat(start_str)
            dt_start = CAMBODIA_TZ.localize(dt_start_naive) if dt_start_naive.tzinfo is None else dt_start_naive

            if end_str:
                dt_end_naive = datetime.fromisoformat(end_str)
                dt_end = CAMBODIA_TZ.localize(dt_end_naive) if dt_end_naive.tzinfo is None else dt_end_naive
            else:
                dt_end = dt_start + timedelta(hours=1)
        else:
            # Fallback to rule-based Khmer event parser
            dt_start, title, location = parse_khmer_event_fallback(user_text, now_local)
            dt_end = dt_start + timedelta(hours=1)
            description = f"{title}" + (f" នៅ {location}" if location else "")

        # Convert to UTC for Google Calendar & iCal
        dt_start_utc = dt_start.astimezone(pytz.utc)
        dt_end_utc = dt_end.astimezone(pytz.utc)

        fmt_google = "%Y%m%dT%H%M%SZ"
        dates_param = f"{dt_start_utc.strftime(fmt_google)}/{dt_end_utc.strftime(fmt_google)}"

        # Generate Google Calendar 1-Click URL
        gcal_params = {
            "action": "TEMPLATE",
            "text": title,
            "dates": dates_param,
            "details": f"{description}\n\n🤖 បង្កើតដោយ Smart Assistant Bot",
        }
        if location:
            gcal_params["location"] = location

        gcal_url = "https://calendar.google.com/calendar/render?" + urllib.parse.urlencode(gcal_params)

        # Generate iCalendar (.ics) content
        fmt_ical = "%Y%m%dT%H%M%SZ"
        now_utc = datetime.now(pytz.utc).strftime(fmt_ical)
        uid = f"{int(dt_start.timestamp())}_{chat_id}@assistantbot.local"
        
        ics_content = (
            "BEGIN:VCALENDAR\r\n"
            "VERSION:2.0\r\n"
            "PRODID:-//Smart Assistant Bot//EN\r\n"
            "CALSCALE:GREGORIAN\r\n"
            "METHOD:PUBLISH\r\n"
            "BEGIN:VEVENT\r\n"
            f"UID:{uid}\r\n"
            f"DTSTAMP:{now_utc}\r\n"
            f"DTSTART:{dt_start_utc.strftime(fmt_ical)}\r\n"
            f"DTEND:{dt_end_utc.strftime(fmt_ical)}\r\n"
            f"SUMMARY:{title}\r\n"
            f"DESCRIPTION:{description}\r\n"
            + (f"LOCATION:{location}\r\n" if location else "") +
            "STATUS:CONFIRMED\r\n"
            "BEGIN:VALARM\r\n"
            "TRIGGER:-PT60M\r\n"
            "ACTION:DISPLAY\r\n"
            f"DESCRIPTION:Reminder: {title} in 60 minutes\r\n"
            "END:VALARM\r\n"
            "END:VEVENT\r\n"
            "END:VCALENDAR\r\n"
        )

        # Schedule automatic reminder exactly 60 minutes before event
        dt_remind_local = dt_start - timedelta(minutes=60)
        dt_remind_utc = dt_remind_local.astimezone(pytz.utc)

        remind_time_display = dt_remind_local.strftime("%I:%M %p, %d/%m/%Y")
        event_time_display = dt_start.strftime("%I:%M %p, %d/%m/%Y")

        reminder_msg = (
            f"⏰ *[សារដាស់តឿនការណាត់ជួប - នៅសល់ ៦០ នាទីទៀត!]* 🔔\n\n"
            f"📌 *កម្មវិធី:* `{title}`\n"
            f"🕒 *ម៉ោងចាប់ផ្តើម:* `{event_time_display}`\n"
            + (f"📍 *ទីតាំង:* `{location}`\n" if location else "") +
            f"\n💡 _សូមរៀបចំខ្លួន និងចេញដំណើរឱ្យបានទាន់ពេលវេលា!_ 🚀"
        )

        # Add to reminders database only if reminder time is in the future
        if dt_remind_utc > datetime.now(pytz.utc):
            add_reminder(
                chat_id=chat_id,
                remind_at=dt_remind_utc.isoformat(),
                remind_time_str=f"មុន ៦០ នាទី ({remind_time_display})",
                message=reminder_msg
            )
            reminder_status = "✅ *បានកំណត់សារដាស់តឿនមុន ៦០ នាទីស្វ័យប្រវត្តិ!* 🔔"
        else:
            reminder_status = "ℹ️ _(កម្មវិធីនេះជិតដល់ម៉ោងពេក មិនអាចកំណត់ដាស់មុន ៦០ នាទីបានទេ)_"

        # Format confirmation response
        msg = (
            "📅 *[បានបង្កើតកម្មវិធីណាត់ជួបជោគជ័យ!]* ✨\n\n"
            f"📌 *កម្មវិធី:* **{title}**\n"
            f"🕒 *កាលបរិច្ឆេទ:* `{event_time_display}`\n"
            f"⏳ *បញ្ចប់នៅ:* `{dt_end.strftime('%I:%M %p')}`\n"
            + (f"📍 *ទីតាំង:* `{location}`\n" if location else "") +
            f"📝 *កំណត់ចំណាំ:* _{description}_\n\n"
            f"{reminder_status}\n\n"
            "👇 _លោកអ្នកអាចចុចប៊ូតុងខាងក្រោមដើម្បីបញ្ចូលទៅក្នុង Google Calendar ភ្លាមៗ ឬទាញយកឯកសារ .ICS!_"
        )

        return True, msg, gcal_url, ics_content

    except Exception as e:
        logger.error(f"Error parsing calendar event: {e}")
        return False, f"❌ កំហុសបច្ចេកទេសក្នុងការបង្កើត Event៖ {str(e)[:120]}", None, None
